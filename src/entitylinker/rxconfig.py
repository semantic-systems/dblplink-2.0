import reflex as rx

config = rx.Config(
    app_name="entitylinker",
    api_url="https://api.dblplink-2.skynet.coypu.org",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ],
)
