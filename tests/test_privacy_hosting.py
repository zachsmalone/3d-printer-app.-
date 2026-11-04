def test_privacy_does_not_claim_a_cloudflare_proxy():
    # DNS-only: traffic goes straight to the VM, so the page must not say it passes through Cloudflare.
    html = open("static/privacy.html").read()
    assert "Cloudflare" not in html
    assert "Google Cloud servers in the United States" in html
