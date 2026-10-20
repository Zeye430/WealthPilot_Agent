"""Simulated back end of the "Zhian Bank mobile app" (demo only; not part of WealthPilot).

In reality this is the bank's own system: customers sign in with their bank account, and tapping "AI
wealth assistant" makes the bank's back end issue
a one-time entry ticket. WealthPilot interacts with it only through signed tickets, sharing no
accounts, passwords or sessions.
Turned off in production (BANK_SIM_ENABLED=false) and replaced by the real mobile banking app.
"""
