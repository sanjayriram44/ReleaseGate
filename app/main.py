from fastapi import FastAPI


def create_app() -> FastAPI:
    return FastAPI(title="CRA Vulnerability Response Service", version="1.0.0")


app = create_app()
