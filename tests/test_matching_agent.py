from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from matching_agent import (
    agent,
    compare_candidates,
    extract_requirements,
    generate_interview_questions,
)


class MatchingAgentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.resume_dir = Path(self.temp_dir.name)
        (self.resume_dir / "Alex_Rivera.txt").write_text(
            "Software engineer with 5 years of experience. React, TypeScript, "
            "Node.js, AWS. Built and tested REST APIs.",
            encoding="utf-8",
        )
        (self.resume_dir / "Sam_Lee.txt").write_text(
            "Frontend developer with 2 years experience. React and JavaScript. "
            "Created responsive web apps.",
            encoding="utf-8",
        )
        (self.resume_dir / "Jordan_Kim.txt").write_text(
            "Backend engineer with 6 years experience. Python, Django, PostgreSQL, AWS.",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def search(self, query: str, **extra):
        return agent.invoke(
            {
                "user_query": query,
                "resume_dir": str(self.resume_dir),
                "conversation_history": [],
                "refinement_round": 0,
                **extra,
            }
        )

    def test_extracts_must_have_nice_to_have_and_experience(self) -> None:
        requirements = extract_requirements(
            "Must-have: React, TypeScript. Nice-to-have: AWS. At least 3 years experience"
        )
        self.assertIn("React", requirements["must_have"])
        self.assertIn("TypeScript", requirements["must_have"])
        self.assertIn("AWS", requirements["nice_to_have"])
        self.assertEqual(requirements["min_years"], 3.0)

    def test_natural_language_search_ranks_candidates(self) -> None:
        state = self.search("Find candidates with React and 3+ years experience")
        self.assertEqual(state["candidate_shortlist"][0]["name"], "Alex Rivera")
        self.assertIn("Sam Lee", state["response"])

    def test_compare_top_matches_side_by_side(self) -> None:
        state = self.search("Find React candidates")
        state = agent.invoke(
            {**state, "user_query": "Compare the top 3 matches side by side"}
        )
        self.assertIn("Candidate comparison:", state["response"])
        self.assertIn("Alex Rivera", state["response"])
        self.assertIn(
            "Alex Rivera",
            compare_candidates([candidate["id"] for candidate in state["candidate_shortlist"][:2]]),
        )

    def test_explains_named_candidate_ranking(self) -> None:
        state = self.search("Find React candidates")
        state = agent.invoke({**state, "user_query": "Why did Alex Rivera rank higher than Sam Lee?"})
        self.assertIn("ranked higher", state["response"])
        self.assertIn("Alex Rivera", state["response"])

    def test_refinement_re_ranks_and_records_history(self) -> None:
        state = self.search("Find React candidates")
        state = agent.invoke({**state, "human_feedback": "Also require at least 4 years experience"})
        self.assertEqual(state["requirements"]["min_years"], 4.0)
        self.assertEqual(state["candidate_shortlist"][0]["name"], "Alex Rivera")
        self.assertGreater(state["refinement_round"], 0)

    def test_refinement_can_replace_a_skill(self) -> None:
        state = self.search("Find React candidates")
        state = agent.invoke(
            {**state, "human_feedback": "Instead of React, use Python"}
        )
        self.assertNotIn("React", state["requirements"]["must_have"])
        self.assertIn("Python", state["requirements"]["must_have"])
        self.assertEqual(state["candidate_shortlist"][0]["name"], "Jordan Kim")

    def test_new_search_replaces_old_requirements(self) -> None:
        state = self.search("Find React candidates")
        state = agent.invoke({**state, "user_query": "Find Python candidates"})
        self.assertEqual(state["requirements"]["must_have"], ["Python"])
        self.assertEqual(state["candidate_shortlist"][0]["name"], "Jordan Kim")

    def test_interview_questions_are_candidate_specific(self) -> None:
        state = self.search("Find React candidates")
        candidate = state["candidate_shortlist"][0]
        state = agent.invoke(
            {**state, "user_query": f"Generate screening questions for {candidate['name']}"}
        )
        self.assertIn("Describe a recent project", state["response"])
        questions = generate_interview_questions(candidate["id"])
        self.assertGreaterEqual(len(questions), 2)
        self.assertTrue(any("project" in question.lower() for question in questions))


if __name__ == "__main__":
    unittest.main()
