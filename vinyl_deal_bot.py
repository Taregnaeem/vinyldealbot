import praw
import re
import time
import logging
from db import *
from commentstrings import *

conn = sqlite3.connect('alerts.db')
c = conn.cursor()
reddit = praw.Reddit('VinylDealBot')
subreddit = reddit.subreddit("vinyldeals")

def removeAllArtists(conn, cursor, comment):
    username = comment.author.name
    artists = get_user_artists(cursor, username)
    created = comment.created_utc
    permalink = comment.permalink
    removedArtists = []
    for artist,created in artists:
        if artist != "" and user_has_artist(cursor, username, artist) \
                and artist_is_active(conn, cursor, username, artist):
            remove_artist_alert(conn, cursor, username, artist, created)
            removedArtists.append(artist)
    if len(removedArtists) > 0:
        logging.info("Removed all alerts for user " + username)
        comment.reply(getRemovedAllCommentString(removedArtists))
        time.sleep(3)
    else:
        reply = "**VinylDealBot**\n\nYou are currently not signed up for any alerts\n\n"
        comment.reply(reply)


def showAlerts(conn, cursor, comment):
    username = comment.author.name
    created = comment.created_utc
    permalink = comment.permalink
    if user_exists(cursor, username):
        artists = get_user_artists(cursor, username)
        mark_comment_read(conn, cursor, username, permalink, created)
        if artists == -1 or len(artists) <= 0:
            reply = "**VinylDealBot**\n\nYou are currently not signed up for any alerts\n\n"
            comment.reply(reply)
        else:
            logging.info("Showing all alerts for user " + username)
            comment.reply(getShowAllCommentString(artists))
            time.sleep(3)


def removeArtists(conn, cursor, comment):
    artists = " ".join(comment.body.split()[2:])
    artists = [ x.lstrip() for x in artists.split(",")]
    username = comment.author.name
    created = comment.created_utc
    for artist in artists:
        if user_has_artist(cursor, username, artist) \
                and artist_is_active(conn, cursor, username, artist) \
                and created > get_artist_timestamp(conn, cursor, username, artist):
            remove_artist_alert(conn, cursor, username, artist, created)
            logging.info("Removed " + artist + " from user " + username)
    if len(artists) > 0:
        comment.reply(getRemoveArtistsCommentString(artists))
        time.sleep(3)


def addArtists(conn, cursor, comment):
    # Get the artist name
    artists = " ".join(comment.body.split()[1:])
    artists = [ x.lstrip() for x in artists.split(",")]

    # Create artist obj
    created = comment.created_utc
    username = comment.author.name
    if not user_exists(cursor, username):
        create_new_user(conn, cursor, username)
    addedArtists = []
    for artist in artists:
        artist = artist.rstrip().lstrip()
        if not user_has_artist(cursor, username, artist):
            insert_artist(conn, cursor, username, artist, created)
            addedArtists.append(artist)
            logging.info(comment.author.name + " wants alerts for " + artist)

        if not artist_is_active(conn, cursor, username, artist) \
                and created > get_artist_timestamp(conn, cursor, username, artist):
            update_artist(conn, cursor, username, artist, created)
            addedArtists.append(artist)
            logging.info(comment.author.name + " wants alerts for " + artist + " (update)")

    if (len(addedArtists) > 0):
        comment.reply(getCommentString(addedArtists))
        time.sleep(3)

def executeCommand(conn, cursor, comment, body):
    if re.search("Remove ", comment.body, re.IGNORECASE) \
            and body[1].lower() == "remove":
        begin_execute = datetime.datetime.now()
        removeArtists(conn, cursor, comment)
        logging.info("Remove Artists...time taken:\t" + str(datetime.datetime.now() - begin_execute))
    elif re.search("RemoveAll", comment.body, re.IGNORECASE) \
            and body[1].lower() == "removeall":
        begin_execute = datetime.datetime.now()
        removeAllArtists(conn, cursor, comment)
        logging.info("Remove All Artists...time taken:\t" + str(datetime.datetime.now() - begin_execute))

    elif re.search("ShowAlerts", comment.body, re.IGNORECASE) \
            and body[1].lower() == "showalerts":
        begin_execute = datetime.datetime.now()
        showAlerts(conn, cursor, comment)
        logging.info("Show Alerts...time taken:\t" + str(datetime.datetime.now() - begin_execute))
    else:
        begin_execute = datetime.datetime.now()
        addArtists(conn, cursor, comment)
        logging.info("Add Artists...time taken:\t" + str(datetime.datetime.now() - begin_execute))


def readPosts(conn, cursor):
    numComments = 0
    start = datetime.datetime.now()
    for submission in subreddit.new(limit=100):
        for comment in submission.comments.list():
            numComments += 1
            if not isinstance(comment, praw.models.MoreComments) and comment.body != "[deleted]":
                username = comment.author.name
                permalink = comment.permalink
                created = comment.created_utc
                body = comment.body.split(" ")
                if re.search("vinyldealbot",comment.body.lower(), re.IGNORECASE) \
                        and body[0].lower() == "vinyldealbot" \
                        and not comment_has_been_read(cursor, username, permalink, created) \
                        and comment.author.name != "VinylDealBot"\
                        and len(body) > 1:
                    mark_comment_read(conn, cursor, username, permalink, created)
                    executeCommand(conn, cursor, comment, body)

    end = datetime.datetime.now()
    logging.info("Comments read: " + str(numComments) + "\tTime Taken: " + str(end - start) + "\tAverage Time(s): " + str((end - start).total_seconds() / numComments))


def send_alert(conn, cursor, reddit, submission, artist, username):
    template = get_template(artist, submission.title, submission.url, submission.permalink)
    create_new_alert_entry(conn, cursor, username, artist, submission.url)
    reddit.redditor(username).message('VinylDealBot: ' + artist + " on sale",  template)
    logging.info("Sent message to " + username + "for " + artist + "\n" + submission.title)


def alert(conn, cursor):
    artists =  get_all_artists(cursor)
    # Iterate through all posts in the top 50 hot posts
    for submission in subreddit.new(limit=100):
        title = submission.title.replace('Lowest', '', 1)
        # check if an artist that a user wants alerts for is in the title
        for artist in artists:
            if re.search(artist, title, re.IGNORECASE):
                users = get_all_users_with_artist(cursor, artist)
                # send users alerts
                for user in users:
                    if not alert_sent(cursor, user, artist, submission.url):
                        send_alert(conn, cursor, reddit, submission, artist, user)

if __name__ == "__main__":
    conn = sqlite3.connect('alerts.db')
    c = conn.cursor()
    logging.basicConfig(filename="vinylbot.log", level=logging.INFO, format="%(asctime)s - %(message)s")
    logging.info("Launching VinylDealBot...")

    while True:
        logging.info("Reading posts")
        readPosts(conn, c)
        logging.info("Checking alerts")
        alert(conn, c)

