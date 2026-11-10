# Feed reliability improvements

The shared Markets JSON loader now bounds requests to 60 seconds, including body parsing. A separate controller is used for each attempt, so a timeout does not poison subsequent polling or manual retries. Unmounting and URL changes cancel requests; late responses cannot replace the active data.

Refresh failures retain the previous successful payload and show its stale status. Failed feeds remain retryable while unrelated feeds are loading. The shared source bar reports browser offline status and distinguishes it from provider errors. This applies to consumers of useJSON, including flight tracking; custom loaders elsewhere are outside this change.

Regression coverage includes stalled bodies, transports ignoring abort, cleanup, old-response isolation, timed-out refresh recovery, non-overlapping polling and metadata honesty. No market calculations or trade submission paths changed.

Validation: 11 focused tests passed; the final cancellation-order adjustment was rechecked with nine reliability tests, all passing. Production build passed with existing bundle-size warnings; git diff whitespace checks passed. Browser visual verification was not performed in this pass.
