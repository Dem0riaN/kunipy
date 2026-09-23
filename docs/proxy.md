# Proxy

Kunipy contains a proxy/web integration subsystem.

The proxy implementation is part of the current Python application and is not
a component inherited from C++ Kuni source code.

Deployment details depend on the current configuration and network environment.

Before exposing a proxy publicly:

- bind only to the required interfaces;
- configure authentication/authorization where applicable;
- restrict access at the network layer;
- avoid exposing administrative endpoints;
- keep credentials outside the repository.
