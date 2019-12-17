# forecast-to-github-migrator
Migrate Forecast cards into Github issues

Required:
- Forecast token
- Github username and token, with proper scope
    - Github scope needed: repo (or public_repo only if not private)
    - or admin if projects needed

Features:
- Issue migrations
- with comments
- filter by forecast project + sprint
- author prefixes for issue and comment bodies
- Add common label to migrated issues on github
- throttle (https://developer.github.com/v3/guides/best-practices-for-integrators/#dealing-with-abuse-rate-limits)
