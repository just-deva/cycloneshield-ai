# Deploying CycloneShield AI to Google Cloud Run

One container serves both the API and the UI, so there is **one URL**: no CORS, no separate hosting, no API-URL build variable.
You do **not** need to install anything locally: use **Cloud Shell** (the terminal icon at the top right of https://console.cloud.google.com).

## 0. What you need
* A Google Cloud project **with billing enabled** (Cloud Run and Cloud Build need it; new accounts get free credits).
* A **Gemini API key on a project with billing** (paid tier): free-tier prompts are used by Google to improve its products, grounding is unavailable, and rate limits are tight. A "Google AI Pro" consumer subscription is *not* the same thing as API billing.
* (Optional but recommended) Earth Engine registration and a Telegram bot.

## 1. Open Cloud Shell and get the code
```bash
gcloud config set project YOUR_PROJECT_ID
git clone https://github.com/YOUR_USER/YOUR_REPO.git cycloneshield && cd cycloneshield
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com earthengine.googleapis.com
```

## 2. Earth Engine (optional, enables live GFS rain and flood-zone population/buildings)
1. Register the project for Earth Engine (non-commercial is fine for the hackathon): https://code.earthengine.google.com/register -> "Unpaid usage" -> your project.
2. Give the Cloud Run runtime service account access:
```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
SA=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com
gcloud projects add-iam-policy-binding $(gcloud config get-value project) --member=serviceAccount:$SA --role=roles/earthengine.viewer
gcloud projects add-iam-policy-binding $(gcloud config get-value project) --member=serviceAccount:$SA --role=roles/serviceusage.serviceUsageConsumer
```
Note: Earth Engine is free for non-commercial use only; a ministry or state pilot would probably need paid Earth Engine.

## 3. Secrets
```bash
printf '%s' 'YOUR_GEMINI_API_KEY' | gcloud secrets create gemini-key --data-file=-
gcloud secrets add-iam-policy-binding gemini-key --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
# optional Telegram bot (create with @BotFather; chat id from @userinfobot)
printf '%s' 'YOUR_BOT_TOKEN' | gcloud secrets create telegram-token --data-file=-
gcloud secrets add-iam-policy-binding telegram-token --member=serviceAccount:$SA --role=roles/secretmanager.secretAccessor
```

## 4. Deploy
```bash
gcloud run deploy cycloneshield --source . --region asia-south1 --allow-unauthenticated \
  --memory 2Gi --cpu 2 --cpu-boost --timeout 300 --min-instances 1 --max-instances 1 \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$(gcloud config get-value project),GEMINI_MODEL=gemini-3.7-flash,TELEGRAM_CHAT_ID=YOUR_CHAT_ID,TELEGRAM_WEBHOOK_SECRET=pick-a-long-random-string \
  --set-secrets GEMINI_API_KEY=gemini-key:latest,TELEGRAM_BOT_TOKEN=telegram-token:latest
```
* `--max-instances 1` keeps the in-memory simulation cache and the file-based audit chain consistent (state is lost on redeploy; production would use Firestore + a retention-locked bucket).
* `--min-instances 1` removes cold starts during judging. It costs money while it runs: **delete the service after evaluation**.
* Leave `TELEGRAM_*` out to run dispatch in labelled simulation mode.

## 5. Telegram acknowledgements (only if you set a bot)
```bash
URL=$(gcloud run services describe cycloneshield --region asia-south1 --format='value(status.url)')
curl -s -X POST "$URL/api/telegram/setup" -H 'Content-Type: application/json' -d "{\"public_url\": \"$URL\"}"
```
Send your bot a message (`/start`) from the phone that should receive advisories, then dispatch an approved advisory: the message arrives with an **Acknowledge receipt** button, and pressing it marks the advisory `ACKED` in the app and audit chain.

## 6. Verify
```bash
curl -s $URL/api/health          # features: gemini / earth_engine / telegram should be true where configured
curl -s $URL/api/gee/status      # Earth Engine connection detail
```
Then open `$URL` in a private window, run the default replay (Hudhud at Visakhapatnam), draft an advisory, submit -> approve (as two different approvers) -> dispatch.

## Troubleshooting
| Symptom | Cause / fix |
|---|---|
| Header chip "Gemini off" | Secret not mounted or wrong name: `gcloud run services describe cycloneshield --region asia-south1` and check env/secrets |
| "Earth Engine" chip off, `/api/gee/status` shows an error | Project not registered for Earth Engine, or the service account lacks `roles/earthengine.viewer` / `serviceusage.serviceUsageConsumer` |
| Advisory shows "TEMPLATE FALLBACK" | Gemini failed or the draft failed validation twice; open **Trust -> AI trace** for the error |
| First page load is slow | Warm-up runs the default simulations at start; keep `--min-instances 1` |
| Telegram message arrives but Acknowledge does nothing | Webhook not set (step 5) or `TELEGRAM_WEBHOOK_SECRET` differs between deploy and `setup` |
