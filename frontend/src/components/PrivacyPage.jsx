/** Plain-language privacy notice, shown from the sign-in screen and the Account page. */
export default function PrivacyPage({ onBack, aiEnabled = false }) {
  return (
    <article className="card mx-auto flex max-w-2xl flex-col gap-4 text-sm leading-relaxed text-ink-2">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-ink">Privacy</h2>
        {onBack && (
          <button type="button" className="btn-ghost" onClick={onBack}>
            ← Back
          </button>
        )}
      </div>

      <section>
        <h3 className="font-semibold text-ink">What's stored</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>Your email, a hash of your password (argon2) and hashes of your login sessions.</li>
          <li>
            The transactions from statements you import (date, amount, balance, description), your bank accounts'
            names, currency and optionally their last 4 digits, plus your categories and rules.
          </li>
        </ul>
      </section>

      <section>
        <h3 className="font-semibold text-ink">What's never stored</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>The statement files themselves: they're read in memory and discarded.</li>
          <li>File names, full account numbers, or your password in readable form.</li>
        </ul>
      </section>

      <section>
        <h3 className="font-semibold text-ink">Who can see it</h3>
        <p className="mt-1">
          Only you, through the app: every request is checked against your account, and other users can't see or
          change anything of yours. As with any web service, the person running this server and the hosting
          provider could technically access the database. It is not end-to-end encrypted. If that matters to
          you, try the app with a sample statement first.
        </p>
      </section>

      <section>
        <h3 className="font-semibold text-ink">AI</h3>
        {aiEnabled ? (
          <p className="mt-1">
            Automatic detection is on. To work out a new statement layout, the column headers and up to 10 rows
            are sent to Anthropic's Claude with names, descriptions and account numbers masked. To suggest
            categories, only cleaned merchant names (never people's names) are sent. Amounts, balances and your
            account details are not sent.
          </p>
        ) : (
          <p className="mt-1">
            On this server automatic detection is turned off: nothing is sent to any AI service. Columns are mapped
            by you (once per bank) and categories come from rules and your corrections.
          </p>
        )}
      </section>

      <section>
        <h3 className="font-semibold text-ink">Your controls</h3>
        <ul className="mt-1 list-disc space-y-1 pl-5">
          <li>
            <strong className="text-ink">Download my data</strong> on the Account page gives you everything stored
            about you as a JSON file.
          </li>
          <li>
            <strong className="text-ink">Delete account</strong> permanently removes your account and all your data.
          </li>
        </ul>
      </section>
    </article>
  );
}
