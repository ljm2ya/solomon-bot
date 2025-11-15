# Slack Event Subscriptions Setup with ngrok

## Quick Setup

### 1. Enter Development Environment
```bash
nix-shell
```

### 2. Start Webhook Server
```bash
python webhook_server.py
```

### 3. Expose with ngrok (New Terminal)
```bash
ngrok http 3000
```

### 4. Configure Slack App

1. **Copy ngrok URL**: Copy the HTTPS URL from ngrok output
   ```
   https://abc123.ngrok.io
   ```

2. **Go to Slack App Settings**: https://api.slack.com/apps

3. **Event Subscriptions**:
   - Toggle ON Event Subscriptions
   - **Request URL**: `https://abc123.ngrok.io/slack/events`
   - Wait for ✅ Verified

4. **Subscribe to Bot Events**:
   - `app_mention`
   - `message.channels`
   - `message.im`
   - `channel_created`

5. **Save Changes** and **Reinstall App**

## Testing

### Verify Webhook
```bash
curl https://your-ngrok-url.ngrok.io/health
```

### Monitor Events
Watch webhook server logs for incoming Slack events.

## Alternative: Socket Mode Only

If you prefer to keep using Socket Mode without webhooks:

1. **Slack App** → **Socket Mode** → Enable
2. **App-Level Token** → Create token with `connections:write`
3. **Event Subscriptions** → Subscribe to bot events (same list)
4. **Keep using your current main.py**

## Files

- `webhook_server.py` - Webhook server for Event Subscriptions
- `main.py` - Socket Mode bot (current implementation)

## Common Issues

- **ngrok URL changes**: Restart ngrok updates the URL - update Slack config
- **Port conflicts**: Change port in webhook_server.py if 3000 is taken
- **SSL required**: Slack requires HTTPS - ngrok provides this automatically