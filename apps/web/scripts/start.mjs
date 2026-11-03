// Local start stays on loopback; the Docker runtime uses server.js directly.
process.env.HOSTNAME = "127.0.0.1";
await import("../.next/standalone/server.js");
