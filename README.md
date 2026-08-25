# SOSODA MARKET — Railway

Telegram Premium shop + admin panel + Premium API.

## Railway
1. Create a Railway project.
2. Add PostgreSQL.
3. Deploy this repository.
4. Add variables:
   - BOT_TOKEN
   - ADMIN_ID=1915699158
   - SUPPORT_USERNAME=@SOSODASTORE
   - API_SECRET
   - DATABASE_URL (normally supplied by the PostgreSQL service)
5. Generate a public domain for the web service.
6. The API endpoint is `/premium/{nick}` with `X-API-Secret` header.

## Bot
Admin: /admin
Grant: /grant NICK DAYS
Remove: /remove NICK
Check: /check NICK
List: /list
Key: /key DAYS

Customers can use /start and the Buy Premium button.

## Security
Never commit .env or the bot token to GitHub.
