"""Builds the golden-set source PDF: a fictional but internally-consistent
Nimbus Cloud Storage support handbook. Real, verifiable content — every
golden Q&A answer is traceable to one exact (page, paragraph) here.

Generated programmatically (like tests/conftest.py's sample_pdf) rather
than committed as a binary, so it stays deterministic and diffable.
"""

import fitz

PAGES: list[list[str]] = [
    [
        "To create a Nimbus account, visit signup.nimbuscloud.example and provide a valid "
        "email address. A verification link is sent immediately; accounts are not active "
        "until the link is confirmed. Free accounts include 15GB of storage.",
        "Two-factor authentication (2FA) can be enabled from Account Settings > Security. "
        "Nimbus supports authenticator apps such as Google Authenticator and Authy; "
        "SMS-based 2FA is not supported for security reasons.",
    ],
    [
        "Nimbus offers three paid tiers: Basic (100GB, $2.99/month), Plus (1TB, "
        "$7.99/month), and Pro (5TB, $19.99/month). All paid tiers include unlimited "
        "file version history for 90 days.",
        "Storage upgrades take effect immediately upon payment. Downgrades take effect "
        "at the start of the next billing cycle, and any files exceeding the new storage "
        "limit are archived in read-only mode rather than deleted.",
    ],
    [
        "Shared links can be set to expire after a specific number of days, or after a "
        "maximum number of downloads, whichever comes first. Link expiration defaults to "
        "30 days if not specified.",
        "Folder sharing permissions include Viewer, Commenter, and Editor. Only the "
        "folder owner or an Editor with 'manage permissions' rights can change another "
        "collaborator's role.",
    ],
    [
        "If the desktop sync client shows a persistent 'Sync Paused' status, the most "
        "common cause is a local disk running below 5GB of free space. Nimbus pauses "
        "sync automatically to avoid partial file corruption.",
        "Repeated sync conflicts on the same file usually indicate the file is open in "
        "an application that locks it for exclusive writing, such as certain database or "
        "CAD tools. Closing the application before syncing resolves most conflicts.",
    ],
    [
        "Annual plans can be refunded in full within 14 days of purchase. Monthly plans "
        "are not refundable, but can be cancelled at any time to stop future charges; "
        "the current billing period remains active until it ends.",
        "Failed payments trigger three retry attempts over 7 days. If all retries fail, "
        "the account is downgraded to the Free tier and files above the 15GB free limit "
        "become read-only until payment succeeds.",
    ],
    [
        "A full data export can be requested from Account Settings > Data Export. "
        "Exports are packaged as a single zip file and a download link is emailed within "
        "24 hours; the link remains valid for 7 days.",
        "Deleting an account is permanent after a 30-day grace period, during which the "
        "account can be reactivated by logging back in. After 30 days, all files and "
        "account data are permanently erased and cannot be recovered.",
    ],
]


def build_golden_source_pdf(output_path: str) -> None:
    doc = fitz.open()
    for paragraphs in PAGES:
        page = doc.new_page()
        y = 50
        for paragraph in paragraphs:
            page.insert_textbox(fitz.Rect(50, y, 550, y + 150), paragraph, fontsize=11)
            y += 200
    doc.save(output_path)
    doc.close()


if __name__ == "__main__":
    import sys

    build_golden_source_pdf(sys.argv[1] if len(sys.argv) > 1 else "golden_source.pdf")
