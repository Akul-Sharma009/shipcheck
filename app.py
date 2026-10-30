"""ShipCheck: pre-judge your hackathon submission before the judges do."""
import streamlit as st

from shipcheck import config, guard
from shipcheck.llm import LLMError
from shipcheck.pipeline import PipelineError, run
from shipcheck.render import LABEL, counts, to_fix, to_markdown
from shipcheck.repo import RepoError, head
from shipcheck.schemas import Report

DEFAULT_HACKATHON = "https://nebiusglobalaihackathon.devpost.com/"
BADGE = {"pass": ":green-background[**PASS**]", "fail": ":red-background[**FAIL**]",
         "unclear": ":orange-background[**UNCLEAR**]", "not_checkable": ":gray-background[**CONFIRM**]"}

st.set_page_config(page_title="ShipCheck", page_icon="🚢", layout="centered")


def md(text: str) -> str:
    """Escape characters Streamlit markdown would interpret ($ = LaTeX)."""
    return (text or "").replace("$", "\\$")


def code_list(items) -> str:
    return " · ".join(f"`{e.replace('`', '')}`" for e in items)


# ---------- running ----------
def show_example(reason: str) -> None:
    ex = guard.examples()
    if ex:
        st.session_state.report = ex[0][1]
        st.session_state.notice = f"{reason} Showing a saved example report instead."
    else:
        st.session_state.notice = reason


def check(hackathon_url: str, repo_url: str, pasted: str, video_url: str, description: str) -> None:
    st.session_state.notice = ""
    if not config.LIVE or config.missing_keys():
        return show_example("Live checks are paused right now.")
    try:
        full_name, sha = head(repo_url)
    except RepoError as e:
        st.session_state.notice = f"error:{e}"
        return
    except Exception:
        st.session_state.notice = "error:Couldn't reach GitHub. Check the repo URL and try again."
        return

    rkey = guard.rules_key(hackathon_url, pasted)
    key = guard.report_key(sha, rkey, video_url.strip() + "\n" + description.strip())
    cached = guard.get_report(key)
    if cached:
        st.session_state.report = cached
        st.session_state.notice = f"Already checked commit `{sha[:7]}`: showing the saved result (no new model calls)."
        return

    runs = st.session_state.get("runs", 0)
    if runs >= config.MAX_RUNS_PER_SESSION:
        return show_example(f"You've used this session's {config.MAX_RUNS_PER_SESSION} live checks.")
    if not guard.reserve_run():
        return show_example("ShipCheck hit today's limit on live checks (it runs on donated credits).")

    rules_hit = guard.get_rules(rkey)
    try:
        with st.status("Checking your submission…", expanded=True) as status:
            report = run(hackathon_url, repo_url, pasted,
                         rules=rules_hit[0] if rules_hit else None,
                         rules_source=rules_hit[1] if rules_hit else "", description=description,
                         video_url=video_url, progress=status.write)
            status.update(label=f"Checked in {report.seconds:.0f}s", state="complete", expanded=False)
    except (PipelineError, RepoError) as e:
        st.session_state.notice = f"error:{e}"
        return
    except LLMError:
        return show_example("The model service didn't respond.")
    st.session_state.runs = runs + 1
    if not rules_hit:
        guard.put_rules(rkey, report.rules, report.rules_source)
    guard.put_report(key, report)
    st.session_state.report = report


# ---------- report card ----------
def render(report: Report) -> None:
    f, rules = report.facts, report.rules
    reqs = {r.id: r for r in rules.requirements}
    c = counts(report)
    fixes = to_fix(report)
    n_fail = sum(1 for x in fixes if x[0] == "fail")

    st.subheader(f"{f.full_name}")
    st.caption(f"Against **{md(rules.hackathon_name)}** · commit [`{f.head_sha[:7]}`]({f.url}/commit/{f.head_sha}) · "
               f"checked {report.created_at[:16].replace('T', ' ')} UTC")
    if n_fail:
        st.error(f"**{n_fail} {'thing' if n_fail == 1 else 'things'} to fix before you submit.**", icon="🚫")
    elif fixes:
        st.warning(f"**No failures, but {len(fixes)} item(s) ShipCheck couldn't confirm.** Make them obvious to a judge.",
                   icon="⚠️")
    else:
        st.success("**Everything ShipCheck can check passes.** Confirm the remaining items yourself.", icon="✅")

    cols = st.columns(4)
    for col, (s, label) in zip(cols, (("pass", "Pass"), ("fail", "Fail"), ("unclear", "Unclear"),
                                      ("not_checkable", "Confirm yourself"))):
        col.metric(label, c[s])

    if fixes:
        st.markdown("#### Fix these first")
        for status, ident, problem, fix in fixes:
            with st.container(border=True):
                st.markdown(f"{BADGE[status]} &nbsp; **{ident}** {md(problem)}")
                if fix:
                    st.markdown(f"**Fix:** {md(fix)}")

    tabs = st.tabs(["Requirements", "Repo checks", "Confirm yourself", "How it was checked"])
    with tabs[0]:
        for v in report.verdicts:
            if v.status == "not_checkable":
                continue
            st.markdown(f"{BADGE[v.status]} &nbsp; **{v.requirement_id}** {md(reqs[v.requirement_id].text)}")
            if v.evidence:
                st.caption("Evidence: " + code_list(v.evidence))
            if v.fix:
                st.caption(f"Fix: {md(v.fix)}")
    with tabs[1]:
        st.caption("Facts from the GitHub API (and YouTube, if you gave a video). No AI involved; these override the model.")
        for ch in report.checks:
            if not ch.required:
                st.markdown(f":gray-background[**INFO**] &nbsp; **{ch.id}** {ch.name} "
                            f":gray[(not required by this hackathon: {ch.status})]")
                continue
            st.markdown(f"{BADGE[ch.status]} &nbsp; **{ch.id}** {ch.name}")
            st.caption(md("; ".join(ch.evidence)) + (f"  \nFix: {md(ch.fix)}" if ch.fix else ""))
    with tabs[2]:
        st.caption("These can't be verified from a repo" + ("" if report.description_checked else
                   " (paste your Devpost write-up above and ShipCheck checks the text ones too)")
                   + ". Tick them off before you hit submit.")
        for v in report.verdicts:
            if v.status == "not_checkable":
                st.checkbox(md(reqs[v.requirement_id].text), key=f"manual_{f.head_sha}_{v.requirement_id}")
                extra = [e for e in v.evidence if not e.startswith("Not verifiable")]
                if extra:
                    st.caption(md("; ".join(extra)))
    with tabs[3]:
        st.markdown(f"**Rules:** {md(report.rules_source)}. {len(rules.requirements)} requirements, "
                    f"{len(rules.criteria)} judging criteria"
                    + (f", submission period {rules.submission_start[:10]} → {rules.deadline[:10]}."
                       if rules.submission_start and rules.deadline else "."))
        st.markdown(f"**Repo:** {f.files_considered} of {f.files_in_tree} files read; "
                    f"license as detected by GitHub: `{f.license_spdx or 'none'}`.")
        role = {config.MODEL_NANO: "Nemotron Nano: one call per file, in parallel",
                config.MODEL_SUPER: "Nemotron Super: rules → checklist, then verdicts",
                config.MODEL_ULTRA: "Nemotron Ultra"}
        rows = [{"Model (Nebius Token Factory)": m, "Job": role.get(m, ""), "Calls": u["calls"],
                 "Tokens in": u["prompt_tokens"], "Tokens out": u["completion_tokens"]}
                for m, u in report.usage.items()]
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)
        st.caption(f"Run time {report.seconds:.0f}s. Rerunning the same commit is served from cache.")
        if report.evidence:
            with st.expander(f"Per-file evidence ({len(report.evidence)} files)"):
                st.dataframe([{"File": e.path, "Purpose": e.purpose, "Calls": ", ".join(e.apis_called),
                               "Models": ", ".join(e.models_used)} for e in report.evidence],
                             hide_index=True, use_container_width=True)

    st.download_button("Download report (Markdown)", to_markdown(report),
                       file_name=f"shipcheck-{f.full_name.replace('/', '-')}-{f.head_sha[:7]}.md")


# ---------- page ----------
st.title("🚢 ShipCheck")
st.markdown("**Pre-judge your hackathon submission before the judges do.** Paste the hackathon and your repo: "
            "ShipCheck reads *that* hackathon's rules live and checks every requirement against your code. "
            "GitHub's own facts override the AI, and every pass must cite a file it actually read, "
            "so it errs toward telling you to fix something, never toward a false all-clear.")

with st.form("check"):
    hackathon_url = st.text_input("Hackathon page (Devpost)", DEFAULT_HACKATHON)
    repo_url = st.text_input("Your GitHub repo", placeholder="https://github.com/you/your-project")
    with st.expander("Also check your Devpost submission (video link, write-up)"):
        video_url = st.text_input("YouTube demo video", placeholder="https://youtu.be/…")
        description = st.text_area("Devpost write-up", height=150,
                                   placeholder="Paste your project description, plus any other text fields "
                                               "(e.g. feedback). Nothing is stored or posted.")
    with st.expander("Rules page won't load? Paste the rules text instead"):
        pasted = st.text_area("Rules text", height=150, label_visibility="collapsed")
    submitted = st.form_submit_button("Check my submission", type="primary", use_container_width=True)

if submitted:
    if not repo_url.strip():
        st.session_state.notice = "error:Enter your GitHub repo URL."
    else:
        check(hackathon_url.strip() or DEFAULT_HACKATHON, repo_url.strip(), pasted, video_url, description)

if "report" not in st.session_state and not submitted:
    ex = guard.examples()
    if ex:
        st.session_state.report = ex[0][1]
        st.session_state.notice = "Example report. Run your own repo above."

notice = st.session_state.get("notice", "")
if notice.startswith("error:"):
    st.error(notice[6:])
elif notice:
    st.info(notice)
if st.session_state.get("report"):
    st.divider()
    render(st.session_state.report)

with st.sidebar:
    st.markdown("### How it works")
    st.markdown("1. **Tavily Extract** reads the hackathon's overview and rules pages.\n"
                "2. **Nemotron Super** turns them into a requirement checklist.\n"
                "3. **GitHub API** facts: visibility, detected license, README, commit dates.\n"
                "4. **Nemotron Nano** summarizes each relevant file, in parallel.\n"
                "5. **Nemotron Super** decides each requirement, citing `file:line`.\n\n"
                "All models run on **Nebius Token Factory**. Your code is read, never executed.")
    ex = guard.examples()
    if ex:
        st.markdown("### Example reports")
        for name, rep in ex:
            if st.button(rep.facts.full_name, key=f"ex_{name}", use_container_width=True):
                st.session_state.report = rep
                st.session_state.notice = "Example report."
                st.rerun()
    st.caption(f"Live checks left this session: {max(0, config.MAX_RUNS_PER_SESSION - st.session_state.get('runs', 0))}")
