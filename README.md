# sdbot

A bot for archiving article for deletion (AfD) discussions ([WP:S](http://no.wikipedia.org/wiki/Wikipedia:S)) at Norwegian Bokmål Wikipedia (no-wp)

## Deployment notes

See https://wikitech.wikimedia.org/wiki/Tool:SDBot

## DB Setup

`sqlite3 sdbot.db` and 

```
CREATE TABLE "closed_requests" (
    id INTEGER NOT NULL PRIMARY KEY,
    name TEXT NOT NULL,
    open_date TIMESTAMP NOT NULL,
    close_date TIMESTAMP NOT NULL,
    open_user TEXT NOT NULL,
    close_user TEXT NOT NULL,
    decision TEXT NOT NULL,
    archive TEXT NOT NULL
);
```
