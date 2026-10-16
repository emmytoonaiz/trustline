# Connecting an Instagram account (prototype)

TrustLine watches the comments on one Instagram professional account. A comment that looks like a
scam produces a **private Telegram alert** with **Hide / Delete / Keep** buttons. Nothing is hidden or
deleted unless the owner taps a button.

This uses Meta's *Instagram API with Instagram Login*. Meta changes dashboard wording from time to
time, so if a label below differs slightly, look for the closest match.

## What you need

- A **Facebook account** (this owns the Meta developer app; it is never shown to Instagram users).
- An **Instagram account** for the brand, switched to a **Professional** account (Business or Creator)
  and set to **public**. Comment notifications are not sent for private accounts.
- The TrustLine server already deployed (it provides the public HTTPS address Meta needs).
- Your own Telegram chat with the bot (alerts arrive there).

## 1. Create the Meta app

1. Go to <https://developers.facebook.com/>, log in with the Facebook account and register as a developer if asked.
2. **My Apps → Create App.** Give it a name (e.g. *TrustLine*), choose the use case **Other**, then app type **Business**.
3. On the app dashboard, **Add product → Instagram** and open **API setup with Instagram login**.

## 2. Add your Instagram account as a tester

While the app is in *development mode*, only accounts you add can use it.

1. In the app dashboard: **App roles → Roles → Add People → Instagram Tester**, and enter the Instagram username.
2. On Instagram (the app or instagram.com): **Settings → Website permissions → Apps and websites → Tester invites**, and **Accept**.

## 3. Get the access token

1. Back on **API setup with Instagram login**, under *Generate access tokens*, click **Add account / Generate token** for the Instagram account and log in.
2. Allow the permissions it asks for (`instagram_business_basic` and `instagram_business_manage_comments`).
3. Copy the token. **Treat it like a password.** It lasts about 60 days; generate a new one before it expires.

## 4. Set the Railway variables

Set these on the `trustline` service (never commit them):

| Variable | Value |
|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | the token from step 3 |
| `INSTAGRAM_APP_SECRET` | the app's secret: **App settings → Basic → App secret** |
| `INSTAGRAM_VERIFY_TOKEN` | any long random string you make up |
| `INSTAGRAM_PAIRING_CODE` | another long random string you make up (used once in Telegram) |

A quick way to make a random string: `python -c "import secrets; print(secrets.token_urlsafe(24))"`.

Optional: `INSTAGRAM_POLL_SECONDS` (default `180`; `0` turns polling off), `INSTAGRAM_POLL_MEDIA`
(how many recent posts to check, default `3`), `INSTAGRAM_API_VERSION` (default `v25.0`).

## 5. Point Meta's webhook at TrustLine (optional but recommended)

On **API setup with Instagram login → Configure webhooks**:

- **Callback URL:** `https://<your-domain>/instagram/webhook`
- **Verify token:** the value of `INSTAGRAM_VERIFY_TOKEN`
- Click **Verify and save**, then switch the **comments** field to *Subscribed*.

Meta documents comment webhooks as needing a *Live* app with Advanced Access, so in development mode they may not
arrive for ordinary comments. That is why TrustLine also **polls** your recent posts every few minutes:
it works in development mode for your own account and needs no review.

## 6. Pair the account with your Telegram chat

In a private chat with the TrustLine bot, send:

```
/instagram YOUR_PAIRING_CODE
```

The bot deletes your message (so the code isn't left in the chat), looks up which Instagram account the
token belongs to, and confirms that alerts for it will arrive in this chat.

## 7. Test it

From a *different* Instagram account, comment on one of the brand account's posts, for example:

> Congratulations! You've won ₦500,000. Send your account number and BVN to claim your prize: bit.ly/claim-now

Within one polling interval (or immediately if the webhook fires) you get a Telegram alert. Tap **Hide comment**
and check the comment disappears for other people. Comments from the account itself are ignored, so test from another account.

## Going beyond your own account

Letting *other* businesses connect their Instagram needs Meta **App Review** (permissions for managing comments),
**Business Verification** (legal documents) and **Advanced Access**, plus a proper "Connect Instagram" login flow
and encrypted token storage per business. This prototype deliberately handles one account with a token kept in an
environment variable.

## Privacy

- Only comments that carry a risk signal (a link, a phone or account number, money, risk words) are checked by the AI.
- An alert keeps a 500-character excerpt, the commenter's username and the verdict for 14 days, then it is deleted.
- Comments that aren't flagged are not stored.
