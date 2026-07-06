from blogbook.extract import extract_article


def test_extract_article_removes_page_noise() -> None:
    html = """
    <html lang="en">
      <head>
        <title>Useful Post</title>
        <meta name="author" content="Ada Lovelace">
      </head>
      <body>
        <nav>Navigation</nav>
        <article>
          <h1>Useful Post</h1>
          <p>This is the useful article text.</p>
          <aside>Related posts</aside>
          <script>alert("tracking")</script>
        </article>
      </body>
    </html>
    """

    article = extract_article(html, "https://example.com/post")

    assert article.title == "Useful Post"
    assert article.author == "Ada Lovelace"
    assert article.language == "en"
    assert "useful article text" in article.text
    assert "Navigation" not in article.text
    assert "Related posts" not in article.text
    assert "script" not in article.html

