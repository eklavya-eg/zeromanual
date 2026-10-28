import uvicorn


def main() -> None:
    uvicorn.run("app.app:app", host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
