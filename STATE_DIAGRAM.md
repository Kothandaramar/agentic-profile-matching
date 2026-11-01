# Agent state machine

```mermaid
stateDiagram-v2
    [*] --> ParseJD
    ParseJD --> ExtractRequirements
    ExtractRequirements --> SearchResumes: retrieve up to 100
    SearchResumes --> RankCandidates: shortlist top 10
    RankCandidates --> GenerateReport: deep match analysis
    GenerateReport --> HumanFeedback
    HumanFeedback --> ExtractRequirements: refine / re-rank (up to 3 rounds)
    HumanFeedback --> [*]: accept report / no feedback
```

The graph stores conversation history, extracted requirements, retrieved candidates,
the ranked shortlist, and per-candidate evidence in its state. Its first screen retrieves
resumes by relevance; detailed scoring and hire/no-hire recommendations then operate on
the top ten. The CLI collects optional human refinements and feeds them back through the
graph for another ranking pass.
