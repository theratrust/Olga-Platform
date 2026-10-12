# Controlled DEV user testing — Olga Coaching

Date: 12 October 2026. Scope: `/opt/olga-coaching-dev`, branch `feature/method-core`, Telegram bot `@Olga_Bondareva_test_bot` (ID `8601253053`). This is a small, observed DEV exercise, not production qualification.

## Launch record and limits

- The `/new` admission fix is commit `231323e` (`Gate new conversations on durable coaching eligibility`). `HEAD`, local `origin/feature/method-core`, and `git ls-remote` all matched `231323e87199025a0f262d118c4361224293bcb4` before launch. The only pre-launch untracked paths were `.dev-backups/` and `artifacts/`.
- The DEV bot uses the current checkout through a bind mount at `/app`. Its process predated the fix. Before restarting it, an online SQLite backup of `dev_bot.db` was saved at `.dev-backups/controlled-dev-launch-20261012T052600Z/dev_bot.db`; SQLite `PRAGMA integrity_check` returned `ok`. Only `docker compose restart bot` was run. The DEV database container was not restarted.
- After restart, the bot container was running and aiogram logged `Start polling` and `Run polling for bot @Olga_Bondareva_test_bot`. Telegram `getMe` returned `ok=true` for the same ID and handle. This verifies process, API access, and polling startup; a tester reply is still needed to verify end-to-end delivery.
- Running DEV settings observed before restart: `DEV_DIRECT_CHAT=true`, `EVALUATOR_SHADOW_ENABLED=true`, and `QUALITY_EVALUATOR_SHADOW_ENABLED=true`. These were not changed. Coaching turns may trigger the two existing background evaluator calls in addition to the response call. Moderation delivery is inactive in this run.
- No prompt, product behavior, PROD service, or `develop` branch was changed. No synthetic coaching or transcription call was made for launch checks.

## Cohort and procedure

Invite one trusted tester first, then at most two more after the first path works. Use private Telegram chats with the DEV handle above. Ask testers to use non-sensitive examples, avoid real client details, and report observations privately to the operator. Do not ask them to paste full coaching transcripts into a shared log. Capture time with timezone, step, expected/observed result, and a screenshot or short redacted excerpt only when needed.

| Step | Tester action | Expected observation / failure to record |
| --- | --- | --- |
| First start | From a fresh account, send `/start` and tap the quiz action. | Welcome and Q1 appear. Record missing media, confusing copy, dead button, delay, or silence. |
| Quiz | Answer Q1–Q3 once each; try one previously used answer button. | One question advances at a time; old button shows an inactive/stale alert and does not change progress or score. Record displayed result and any duplicate advancement. |
| Coaching entry | Use the current result/entry button. | Coaching entry opens. A message before completed entry must not grant access. Do not use `/new` as a shortcut from an ineligible account; if tried, it must direct the tester to `/start`. |
| Text | Send one ordinary non-sensitive situation, then one contextual follow-up. | Acknowledgement and one coherent response per turn. Record missing, repeated, truncated, irrelevant, or fact-inventing replies and approximate latency. Keep the total small. |
| Voice/audio | Send one short voice note or supported audio file. | One transcription-based coaching turn and one reply. Record silence, duplicate reply, recognition failure, or confusing audio handling. Do not include private client audio. |
| Contextual home | Send `/start` after coaching entry; choose Continue. | Home shows a Continue path and returns to the current conversation without rerunning the quiz or generating a reply merely from the tap. An old Continue button should be inactive. |
| Restart recovery | An already eligible tester whose conversation existed before the 12 October DEV restart sends one text or voice message without tapping Continue. | The first message is processed once in the same conversation. This is feasible for an existing tester now. Do not restart again solely for this test; if no such tester exists, mark live recovery **not tested** and rely on the offline recovery tests until a coordinated DEV-only window. |
| `/new` | At the end, an eligible tester sends `/new`, then one short text. | Bot announces a new conversation and responds. Prior context should not leak into the new reply. This intentionally clears the tester's old chat history and pending drafts. Record any missing reply or old-context reference. |
| Moderation | Run only if a future DEV run has `DEV_DIRECT_CHAT=false`; current run is direct chat. | In moderated mode, record acknowledgement, admin draft arrival, approval/edit/reject result, and whether user delivery follows the chosen action. Do not toggle the mode for this cohort. |
| Errors | During the above, note visible generic errors, unanswered turns, old-button alerts, unexpected duplicate messages, and excessive delay. | Link each observation to time, step, and redacted evidence; do not provoke provider failures or run extra model probes. |

The interrupted quiz is volatile. If the bot restarts while a quiz is in progress, old buttons should fail safely; the tester sends `/start` and begins at Q1. Plain text before `/start` may receive no guidance. The known concurrent `/new` ordering limit is outside this small sequential protocol; do not stress it with simultaneous messages.

## Manual observation and decision

For each tester use a local private sheet: anonymous tester code, Telegram test account identifier known only to the operator, start/end time and timezone, DEV bot handle, step, pass/fail/not tested, approximate response time, expected versus observed behavior, and a redacted evidence reference. Note whether the account was fresh or previously eligible, whether direct or moderated mode was active, and whether the turn followed a restart. Record the first failure time and stop that tester path if state or privacy seems wrong. Do not copy tokens, full transcripts, raw voice files, or database rows into the sheet.

**Pass for a small DEV cohort:** 1–3 testers can complete their applicable path; no ineligible coaching entry; quiz and stale buttons do not advance incorrectly; eligible text and voice produce at most one user-visible coaching reply per turn; contextual `/start` and `/new` behave as above; no critical unhandled error or cross-conversation disclosure. Mark any unrun scenario `not tested`, especially live restart recovery or moderation. **Stop and investigate:** eligibility bypass, wrong bot identity, cross-user or prior-conversation content, duplicate send, persistent silence after a normal action, repeated provider/Telegram failure, or loss of verified result. A cosmetic copy concern or one recoverable transcription miss is logged but does not by itself stop the cohort.

Read-only observability: `cd /opt/olga-coaching-dev && docker compose ps`; `docker compose logs --since=30m --tail=200 bot` or `docker logs --timestamps olga_bot_container_dev`. Filter for `returning_user_state_restored`, `quiz_callback_rejected`, `new_conversation_rejected`, `ADMISSION_REJECTED`, `SHADOW_EVAL_`, `QUALITY_SHADOW_EVAL_`, `ERROR`, and Telegram polling failures. Existing logs may contain IDs or exception details, so keep raw logs restricted. Evaluation artifacts are under `artifacts/evaluation/`; do not add new evaluator runs for this launch.

The backup above is a recovery point, not a routine rollback command. If the bot misbehaves, stop new tester interactions and inspect DEV logs first. Restore SQLite only after deciding how to handle tester writes made since the backup; a restore would discard them. If code rollback is required, change only the DEV checkout or service in a separate reviewed action. Do not point the DEV bot at PROD credentials or data.

## Short Russian message for Olga

Ольга, мы начинаем небольшой тест DEV-бота: [@Olga_Bondareva_test_bot](https://t.me/Olga_Bondareva_test_bot). Пожалуйста, используй личный чат и не отправляй реальные данные клиенток.

1. Напиши `/start`, пройди короткий тест и нажми кнопку входа в диалог. Проверь, что старые кнопки не запускают шаг повторно.
2. Отправь одно короткое текстовое сообщение о нейтральной ситуации, затем один уточняющий ответ. После этого попробуй короткое голосовое сообщение.
3. Напиши `/start` ещё раз и нажми «Продолжить». В конце попробуй `/new`: он начинает новый разговор и очищает прежнюю историю в этом тестовом чате.

Если кнопка не работает, ответа нет или ответ кажется неверным, пришли мне время, действие и короткий скриншот без личных деталей. Если тест прервётся посреди вопросов, отправь `/start` и начни тест заново. Пока проверяем только этот DEV-бот.
