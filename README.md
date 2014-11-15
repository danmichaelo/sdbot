== SDBot ==

A bot for archiving article for deletion (AfD) discussions ([WP:S](http://no.wikipedia.org/wiki/Wikipedia:S)) at Norwegian Bokmål Wikipedia (no-wp)

See the bots [user page](http://no.wikipedia.org/wiki/Bruker:SDBot) on no-wp for more information. 

To see available command-line switches, run <code>python sdbot.py -h</code>

DB Setup: <code>sqlite3 sdbot.db</code> and 
````
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
````

