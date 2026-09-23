# OpenAI-compatible proxy

Kunipy includes a FastAPI/Uvicorn proxy that can expose the character as an
OpenAI-compatible endpoint.

## Startup

Enable the proxy in configuration:

```toml
[capabilities.proxy]
enabled = true
port = 8080
```

> The exact configuration section should be checked against the current
> `src/config.py` when deploying, because historical configuration examples
> contain naming drift.

The application starts Uvicorn on:

```text
0.0.0.0:<configured-port>
```

## Chat completions

The main intercepted endpoint is:

```text
POST /v1/chat/completions
```

The proxy can:

- inject the character system prompt;
- expose selected tools;
- execute tool calls locally;
- repeat the upstream tool-calling loop;
- return the final assistant response.

The client does not receive the internal tool-call round trips.

## Other endpoints

The implementation is designed to forward other OpenAI-compatible routes,
including embeddings, image generation, audio and models, to the upstream
endpoint.

## Streaming

`stream=true` is supported at the HTTP/SSE interface, but it is not equivalent
to true token-by-token upstream streaming for the intercepted tool-calling
path.

The proxy may complete the full internal tool loop first and then emit the
final answer as SSE.

## Security

The proxy binds to `0.0.0.0` by default.

Do not expose it directly to an untrusted network without an appropriate
network boundary, reverse proxy, authentication layer, or firewall policy.
