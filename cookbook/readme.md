## This is a cookbook for using eGet api for scraping or crawling the URL and creating a RAG ready dataset
To start using the examples in the code, clone the repo and start the docker container

```
git clone https://github.com/vishwajeetdabholkar/eGet-Crawler-for-ai.git 
```

Once the repo is clone do the docker setup:


1. Build the Docker image:
```bash
docker build -t eget-scraper .
```

2. Run with Docker Compose:
```bash
docker-compose up -d
```

Once the docker continer is up, run below commands:
`cd cookbook/playground`
`python -m http.server 8080`

This will stat an simple playground app on : `http://localhost:8080/playground.html`
Go ahead, input URL and checkout the RAG ready results!