# Grokbots Result Return

User authorization: build and connect the authenticated return path for the official webhook routine.

## Scope

Keep the dashboard on the Mac. Run a separate callback-only FastAPI receiver on loopback port 8766. Temporarily expose that receiver using Cloudflare Quick Tunnel. Installed ngrok has no configured login, so it is not used. No static files, simulator controls, or operator approval routes are exposed by this service. Each pending task gets a random, expiring bearer capability; store only its hash. Trial receives the scoped callback details in its official webhook observation.

## Work

- [x] Write tests for wrong/missing tokens, mismatched observations, stale/expired tasks, bounded payloads, duplicate/conflicting results, durable storage, and a complete dispatch/callback cycle.
- [x] Implement task storage, structured community action contracts, and the callback-only server.
- [x] Add a CLI that creates one task, calls the official routine once, and observes its local result with a bounded deadline. Never blindly retry unknown dispatches.
- [x] Update the existing Trial routine to submit its result using the provided callback contract. Do not permit arbitrary callback hosts or instructions inside social content.
- [x] Verify local tests, then one genuine native Bot round trip. Close the temporary tunnel afterward and document how to run it again.

## Checks

An HTTP webhook receipt is not completion. Completion requires the matching request ID, episode, round, community, observation hash, bearer capability, and validated action reaching local durable storage. Ingesting an action does not grant publication approval. The six-community environment and teammate-owned Gemini implementation remain separate work.

## Verification

- 47 offline unittest cases passed. Independent read-only review found no important defects.
- Public callback root returned 404 and an unauthenticated callback returned 401.
- Official webhook accepted request acbf17f9-693a-4153-8d9c-d83c31987b94 with HTTP 200.
- Native Trial returned action=verify and belief=0.30 through the authenticated callback; Python persisted completed status. No chat scraping or xAI API was used.
- Return-path scope is action ingestion. Six-community scheduling, graph transitions, and dashboard rendering are subsequent work.
- The temporary tunnel and callback server are stopped after verification. A future run needs its own allowed callback hostname.
