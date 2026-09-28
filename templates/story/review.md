## Findings
<!-- A card, story or anomaly named in a finding reads `<id> : <short title>` (`s004 : Share a list`), never the bare id. -->
1. <short title> — <finding> — proof: <path:line or command> — matters because: <what breaks if not fixed> — severity: blocking | to-decide | note

## Reinforced checks
- bite: <invariant> — bit | did not bite — `<command>`
- adversarial-review: <angle> — <result>

Verdict: yes | no
Tree: <code tree id printed by `deliveryctl story status <id>`>
Command: <command that replays the decisive check>
Result: <exit code and counts>
By: story-reviewer
