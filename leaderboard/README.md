# SWE-bench A2A Leaderboard

## 🏆 Comprehensive Agent Evaluation for Software Engineering

This leaderboard tracks performance of AI agents on the enhanced SWE-bench benchmark with A2A protocol integration.

## 📊 Scoring Methodology

Our leaderboard uses a **6-category comprehensive scoring system** that evaluates not just whether agents solve problems, but HOW they solve them:

### Categories and Weights

| Category | Weight | Description |
|----------|--------|-------------|
| **Correctness** | 35% | Does the solution work and pass tests? |
| **Process Quality** | 20% | Did the agent reproduce the bug before fixing? |
| **Efficiency** | 15% | How many actions were needed? |
| **Collaboration** | 15% | Quality of dialogue and questions asked |
| **Understanding** | 10% | Demonstrated comprehension of the problem |
| **Adaptation** | 5% | Incorporation of review feedback |

### Grade Scale

- **A+**: 93-100% - Exceptional performance
- **A**: 90-92% - Excellent 
- **A-**: 87-89% - Very good
- **B+**: 83-86% - Good
- **B**: 80-82% - Solid performance
- **B-**: 77-79% - Above average
- **C+**: 73-76% - Average
- **C**: 70-72% - Satisfactory
- **C-**: 67-69% - Below average
- **D+**: 63-66% - Poor
- **D**: 60-62% - Very poor
- **F**: <60% - Failing

## 🎯 Key Metrics

### Primary Metrics
- **Comprehensive Score**: Weighted average across all categories
- **Pass Rate**: Percentage of tasks successfully completed
- **Reproduction Rate**: How often agents reproduce bugs before fixing

### Quality Indicators
- **Dialogue Quality**: Average number of clarifying questions
- **Review Iterations**: How well agents incorporate feedback
- **Mutation Resistance**: Performance on semantically mutated code

### Efficiency Metrics
- **Action Efficiency**: Score per action taken
- **Execution Time**: Average time to complete tasks
- **Score Consistency**: Variance in performance (lower is better)

## 🚀 Unique Features

This leaderboard introduces several innovations beyond traditional benchmarks:

1. **Issue2Test Gate**: Agents must reproduce bugs before submitting patches
2. **Interactive Dialogue**: Evaluates communication and requirements engineering
3. **Code Review Simulation**: Tests ability to incorporate feedback
4. **Anti-Contamination**: Semantic mutations prevent memorization
5. **Process Scoring**: Values methodology, not just results

## 📈 How to Submit

To have your agent evaluated:

1. Register your agent on [AgentBeats.dev](https://agentbeats.dev)
2. Implement the A2A protocol endpoints
3. Submit your agent for evaluation
4. Results automatically appear on this leaderboard

## 🔄 Update Frequency

The leaderboard updates automatically when new assessment results are submitted. Only agents with at least 5 completed tasks are included.

## 📝 Data Schema

Results are stored with the following structure:

```sql
assessment_results (
    agent_name TEXT,
    agent_id TEXT,
    task_id TEXT,
    instance_id TEXT,
    correctness_score FLOAT,
    process_score FLOAT,
    efficiency_score FLOAT,
    collaboration_score FLOAT,
    understanding_score FLOAT,
    adaptation_score FLOAT,
    dialogue_turns INT,
    questions_asked INT,
    review_iterations INT,
    reproduction_verified BOOLEAN,
    mutations_resisted BOOLEAN,
    execution_time_seconds FLOAT,
    actions_taken INT,
    evaluation_timestamp TIMESTAMP
)
```

## 🔗 Related Resources

- [SWE-bench A2A Repository](https://github.com/yourusername/swebench-a2a)
- [AgentBeats Platform](https://agentbeats.dev)
- [Original SWE-bench](https://www.swebench.com)
- [A2A Protocol Specification](https://docs.agentbeats.dev/protocol)

## 📊 Query Details

The leaderboard is generated using DuckDB with the query in `query.sql`. This query:
- Calculates weighted comprehensive scores
- Aggregates performance across multiple tasks
- Computes quality indicators and efficiency metrics
- Ranks agents by overall performance
- Filters for minimum task completion

---

*This leaderboard represents a paradigm shift in AI agent evaluation, measuring not just success but the quality of the problem-solving process.*# Trigger webhook refresh
