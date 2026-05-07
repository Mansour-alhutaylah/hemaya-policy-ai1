import { clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs) {
  return twMerge(clsx(inputs))
}


export const isIframe = window.self !== window.top;

// Prefix for AI Assistant chat history kept in sessionStorage. The key is
// scoped per user (`<prefix><userId|email>`) so two accounts on the same
// browser cannot see each other's conversation.
//
// The `_v2_` token bumps the schema: v1 entries (which incorrectly persisted
// timeout/error bubbles) are no longer read, and clearAssistantSessions
// sweeps both versions so old broken history can never reappear.
export const ASSISTANT_CHAT_PREFIX = "himaya_ai_assistant_chat_v2_";
const ASSISTANT_CHAT_LEGACY_PREFIX = "himaya_ai_assistant_chat_";

/**
 * Remove every AI Assistant chat entry from sessionStorage. Called from all
 * logout paths (manual logout, 401 handler, inactivity timeout) so we never
 * leak a previous user's conversation into the next session. Sweeps the
 * legacy v1 prefix as well so users upgrading from a broken build don't
 * inherit corrupted history.
 */
export function clearAssistantSessions() {
  try {
    const toRemove = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k && k.startsWith(ASSISTANT_CHAT_LEGACY_PREFIX)) toRemove.push(k);
    }
    toRemove.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    // sessionStorage may be unavailable (private mode, quota); not fatal.
  }
}

/**
 * Best-effort one-shot cleanup of pre-v2 keys. Safe to call on every page
 * load — a no-op if nothing matches.
 */
export function purgeLegacyAssistantSessions() {
  try {
    const toRemove = [];
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (
        k &&
        k.startsWith(ASSISTANT_CHAT_LEGACY_PREFIX) &&
        !k.startsWith(ASSISTANT_CHAT_PREFIX)
      ) {
        toRemove.push(k);
      }
    }
    toRemove.forEach((k) => sessionStorage.removeItem(k));
  } catch {
    /* noop */
  }
}
