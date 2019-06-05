# To be used with https://archive.org/details/14566367HackerNewsCommentsAndStoriesArchivedByGreyPanthersHacker

import json
import sys
import sqlite3


def main(db):
    with open("14m_hn_comments_sorted.json") as fd:
        for i, line in enumerate(fd):
            x = json.loads(line)

            if i >= 1_000_000:
                break

            if (i + 1) % 1_000 == 0:
                print("Processing {:,} / 14,566,367 ...".format(i + 1), end="\r")

            try:
                process(db, x)
                """
                if r:
                    sys.stdout.write("\033[K")  # clear
                    print("Skipped {:,}:".format(i + 1), r)
                """
            except KeyError as err:
                pass

def process(db, x):
    if x["source"] != "firebase":
        return "not firebase"

    item = x["body"]

    if item["type"] not in ["story", "comment"]:
        return "bad type: " + item["type"]

    if item.get("dead") or item.get("deleted"):
        return "dead or deleted"

    db.execute('INSERT OR IGNORE INTO "user" (username) VALUES (?);', (item["by"],))
    user_id = db.execute('SELECT id FROM "user" WHERE username = ?', (item["by"],)).fetchone()[0]

    db.execute('INSERT INTO item (id, user_id, "time") VALUES (?, ?, ?);', (item["id"], user_id, item["time"]))

    if item["type"] == "story":
        if "url" in item:
            db.execute('INSERT INTO story (id, title, url, score) VALUES (?, ?, ?, ?);', (item["id"], item["title"], item["url"], item["score"]))
        else:
            db.execute('INSERT INTO story (id, title, "text", score) VALUES (?, ?, ?, ?);', (item["id"], item["title"], item.get("text", ""), item["score"]))
    elif item["type"] == "comment":
        db.execute("""
            INSERT INTO "comment" (
                id,
                "text",
                parent,
                story_id
            ) VALUES (
                ?,
                ?,
                ?,
                ( SELECT coalesce(
                    (SELECT story_id FROM "comment" WHERE id = ?),
                    ?
                ))
            );""", (
                item["id"],
                item["text"],
                item["parent"],
                item["parent"], item["parent"]
            ))

    return False


if __name__ == '__main__':
    with sqlite3.connect("hn.sqlite3", isolation_level=None) as db:
        db.execute("PRAGMA page_size = 65536;")
        db.execute("VACUUM;")
        db.executescript("""
            CREATE TABLE "user" (
                id       INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE
            );

            CREATE TABLE item (
                id      INTEGER PRIMARY KEY,
                -- Instead of `by` field in the API
                user_id INTEGER REFERENCES user NOT NULL,
                "time"  INTEGER NOT NULL
            );

            CREATE TABLE story (
                id     INTEGER PRIMARY KEY REFERENCES item,
                title  TEXT NOT NULL,
                url    TEXT,
                "text" TEXT,
                score  INTEGER NOT NULL,
                CHECK ((url IS NULL AND "text" IS NOT NULL) OR (url IS NOT NULL AND "text" IS NULL))
            );

            CREATE VIRTUAL TABLE story_fts USING fts4(
                content="story",
                tokenize=porter,
                title,
                url,
                "text"
            );

            CREATE TABLE "comment" (
                id       INTEGER PRIMARY KEY REFERENCES item,
                "text"   TEXT NOT NULL,
                parent   INTEGER NOT NULL REFERENCES item,
                story_id INTEGER NOT NULL REFERENCES story
            );

            CREATE VIRTUAL TABLE comment_fts USING fts4(
                content="comment",
                tokenize=porter,
                "text"
            );
        """)
        db.execute("PRAGMA synchronous = NORMAL;")
        db.execute("PRAGMA journal_mode = MEMORY;")
        db.execute("BEGIN;")
        try:
            main(db)
        except KeyboardInterrupt:
            print("\nGracefully...")
        finally:
            print("\nPopulating FTS...")
            db.execute('INSERT INTO story_fts (docid, title, url) SELECT id, title, url FROM story WHERE url IS NOT NULL;')
            db.execute('INSERT INTO story_fts (docid, title, "text") SELECT id, title, "text" FROM story WHERE "text" IS NOT NULL;')
            db.execute('INSERT INTO comment_fts (docid, "text") SELECT id, "text" FROM "comment";')

            db.execute("COMMIT;")
            print("Successfully committed!")
            db.executescript("""
                INSERT INTO story_fts(story_fts) VALUES('optimize');
                INSERT INTO comment_fts(comment_fts) VALUES('optimize');
                CREATE INDEX story_id_idx ON comment (story_id);
                PRAGMA optimize;
                VACUUM;
            """)
            print("Optimizations done!")
