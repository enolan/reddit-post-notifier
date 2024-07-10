This is my script for getting notifications of certain new reddit posts to my phone. It runs a set
of searches every 5 minutes and sends a push notification of any new posts that match the searches.

# Usage instructions

1. `poetry install`
2. [Set up a Pushbullet API token](https://www.pushbullet.com/#settings), and make sure you have the
   app set up on your phone.
3. `mv searches.yml.example searches.yml` and edit it with the searches you want to run.
4. `PUSHBULLET_API_TOKEN=your_token poetry run python reddit_post_notifier`
5. You should get a bunch of notifications, of every post matching your searches made in the last
   week. After that, you should get notifications of new posts every 5 minutes.