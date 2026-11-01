# 5–6 minute demo recording script

Use the included synthetic resumes. From the project folder, start with:

```powershell
python app.py --resume-dir resumes
```

| Time | Demo and narration |
|---|---|
| 0:00–0:40 | Introduce the project as a local LangGraph candidate-screening assistant. Mention that the sample resumes are synthetic and that the tool supports TXT, Markdown, PDF, and DOCX files. |
| 0:40–1:20 | Show [STATE_DIAGRAM.md](./STATE_DIAGRAM.md). Explain the graph path: parse the request, extract requirements, retrieve up to 100 resumes, deeply rank the top 10, generate an evidence-based report, and accept optional human feedback. |
| 1:20–2:15 | Search: `Find me candidates with React and 3+ years experience`. Point out Alex's matching skills and experience, Sam's experience gap, and Jordan's missing React evidence. |
| 2:15–3:00 | At the prompt, press Enter to continue. Ask `Compare the top 3 matches side by side`. Explain that the response compares scores, strengths, and gaps. |
| 3:00–3:40 | Ask `Why did Alex Rivera rank higher than Sam Lee?`. Show how the explanation traces the ranking to matched skills and the experience threshold. |
| 3:40–4:35 | Search again for `Find React candidates`. At the refinement prompt enter `Instead of React, use Python`. Show that the graph re-runs screening and Jordan becomes the top match. |
| 4:35–5:10 | Ask `Generate screening questions for Jordan Kim`. Point out the project-evidence questions grounded in candidate gaps or matched requirements. |
| 5:10–5:40 | Show test coverage by running `python -m unittest discover -s tests -v`. Close by noting that hiring recommendations are decision support and require human review. |

Recording tip: keep the terminal font readable and use the sample dataset so candidate
names and results match the script. Avoid recording real candidate data or personal
information.
