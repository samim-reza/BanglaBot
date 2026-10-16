"""Live conversation scenarios: the real engine and model against an LLM-played caller, graded by code + an LLM judge.

No database, no phone. Costs a little OpenAI usage (gpt-5.4-mini for the agent, the caller and the judge).

    venv/bin/python -m scripts.scenarios                      # everything
    venv/bin/python -m scripts.scenarios --only clinic.       # ids starting with "clinic."
    venv/bin/python -m scripts.scenarios --only clinic.happy,restaurant.pickup --repeat 3
    venv/bin/python -m scripts.scenarios --failed .scenario-reports/<run>/results.json   # re-run what failed
"""
