"""Interactive command-line interface for the candidate matching agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from matching_agent import AgentState, agent


def run_cli(resume_dir: Path) -> None:
    state: AgentState = {
        "resume_dir": str(resume_dir),
        "conversation_history": [],
        "refinement_round": 0,
        "max_refinement_rounds": 3,
    }
    print("Candidate Matching Agent (type 'quit' to exit)")
    print(f"Resume folder: {resume_dir.resolve()}")
    while True:
        try:
            query = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return
        if query.lower() in {"quit", "exit", "q"}:
            print("Goodbye.")
            return
        if not query:
            continue
        state["user_query"] = query
        try:
            state = agent.invoke(state)
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            print(f"Agent error: {exc}")
            continue
        print(f"\nAgent:\n{state.get('response', '')}")
        if state.get("intent") == "search" and state.get("candidate_shortlist"):
            try:
                feedback = input(
                    "\nRefine requirements? (Enter to continue, or describe a change): "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                return
            if feedback:
                state["human_feedback"] = feedback
                try:
                    state = agent.invoke(state)
                    print(f"\nAgent (refined):\n{state.get('response', '')}")
                except (FileNotFoundError, RuntimeError, ValueError) as exc:
                    print(f"Agent error: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search and screen resumes with LangGraph.")
    parser.add_argument(
        "--resume-dir",
        type=Path,
        default=Path("resumes"),
        help="Folder containing TXT, Markdown, PDF, or DOCX resumes (default: ./resumes)",
    )
    args = parser.parse_args()
    run_cli(args.resume_dir)


if __name__ == "__main__":
    main()
