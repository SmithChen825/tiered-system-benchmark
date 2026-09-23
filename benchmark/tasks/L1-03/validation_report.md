# L1-03 Validation Report

Validated 2026-08-29. The first reset failed exactly `test_contact_form_loads_existing_validation_script`; Chromium observed `/assets/contact-validation.js` returning HTTP 404 and confirmed that neither invalid nor valid submission produced the required status. The researcher-authored one-line script-source oracle passed all five hidden source checks. Chromium then observed `/assets/contact-form.js` returning HTTP 200, the frozen invalid-input error, the valid-submission success confirmation, and the form reset. An independent second reset reproduced the same source and browser failures.

Separate baseline and oracle Nginx images were built from the frozen Dockerfile. Browser interaction against both containers reproduced the baseline failure and oracle success respectively, while an unknown path returned HTTP 404 in both containers. Fixture SHA-256: `e896ca6d951c68ea455fa57bb68b72635e7bcc72777171cecc063c24edc5788c`.

Result: **PASS**.

