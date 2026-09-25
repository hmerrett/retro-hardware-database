"""Who may sign in, and what each of them may do (ADR-0032).

`roles` holds the one question the rest of the app asks -- `can(principal,
permission)` -- and the table it is answered from. `store` makes, checks and ends
the accounts, sessions and tokens behind a principal. `firstrun` is the state an
installation is in before it has any accounts. `__main__` is the command an
administrator manages them with from the server.

The gate that reads all of this, and the doors people come through, stay in
`auth.py`.
"""
