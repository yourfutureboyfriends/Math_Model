# Several funds on one platform

The platform can run several funds side by side (e.g. your own fund and BIFS). Pick the fund in the
top-bar **Fund** switcher (shown once there are two or more funds you can open); the app sends it as
the `X-Fund` header and the server routes every book operation to that fund's own database.

| Kept separate per fund (own database)                         | Shared by all funds                              |
|---------------------------------------------------------------|--------------------------------------------------|
| positions, cost basis, FX rates of fills                      | sign-in, accounts and roles                      |
| trade ideas, orders, trades / blotter                         | market data, research panels, the macro model    |
| NAV history and snapshots                                     | Quant Lab, LEAN runs and the paper traders       |
| fund settings: name, capital, base currency, benchmark, mandate | alerts, journal, watchlists                     |
| risk limits                                                   | Daily Brief                                      |
| analyst pitches and PMC decisions                             |                                                  |
| audit log                                                     |                                                  |

* `main` is the original application database (`api/macro_terminal.db`); nothing was moved.
  Other funds live in `api/funds/<id>.db` (gitignored).
* The registry (`funds` table in the main database) holds id, display name and members. A fund with
  no members is open to every signed-in user; otherwise only its members and admins can open it.
  Requests for a fund you cannot open get 403 `fund_forbidden`; an unknown fund gets 404.
* Background jobs (daily NAV snapshot and catch-up) run once per fund.

## Managing funds

* Create: `POST /api/v1/funds` (PM or admin) with `{id, name, base_currency, benchmark, capital, members}`.
* Rename or set members: `PUT /api/v1/funds/{id}` (admin) with `{name, members}`.
* Capital, base currency, benchmark and mandate: switch to the fund, then use the fund settings panel
  (`PUT /api/v1/fund/settings`).
