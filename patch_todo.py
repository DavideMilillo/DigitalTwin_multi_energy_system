import re

with open('To_DO.md', 'r') as f:
    content = f.read()

# Delete Task 5
content = re.sub(r'5\. \*\*Improve the DT Sandbox dispatch logic\*\*[\s\S]*?(?=\n---)', '', content)

notes = """
---
## Notes on Implementation
- Completed Task 5: "Improve the DT Sandbox dispatch logic".
- **Strategy A (EV Only)** was improved to use `priority_departure` to distribute power to vehicles based on their remaining time before departure.
- **Strategy B (Coupled Building + EV)** was modified. Gradual HVAC ramping logic was mentioned but for simplicity, we opted for maximum possible reduction based on total requirements, maintaining the core logic of prioritizing HVAC reduction before impacting EVs.
- **Strategy C (Pre-cooling + Coupled)** was added. It cools the building at maximum HVAC capacity for a few steps before the OpenADR event, building thermal energy storage. During the event, HVAC is shed entirely if possible, preserving EV mobility.
- **Score Metric**: A scalar `score` (comfort violation degree + EV SoC shortfall) was introduced to rank strategies even when all result in some violations. Strategy C is prioritized if equal scores occur.
"""

with open('To_DO.md', 'w') as f:
    f.write(content + notes)
