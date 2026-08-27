# SOSODA MARKET — Railway FINAL

Variables on SOSODAMARKET:
BOT_TOKEN=<your token>
ADMIN_ID=1915699158
SUPPORT_USERNAME=@SOSODASTORE
API_SECRET=<long random secret>
DATABASE_URL=${{Postgres.DATABASE_URL}}

If the PostgreSQL service has another name, replace Postgres with that service name.

Bot: /start /admin /grant NICK DAYS /remove NICK /check NICK /list /key DAYS
API: GET /, GET /premium/{nick}, and POST /activate with X-API-Secret header. /activate redeems one unused key for the specified nick.
