/** Redux unwrap rejects with a serialized error rather than an Error instance. */
export function authErrorMessage(error: unknown, fallback: string): string {
  if (error && typeof error === 'object' && 'message' in error
      && typeof error.message === 'string' && error.message.trim()) {
    if ('name' in error && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
      return 'The server took too long to respond. Please try again.';
    }
    return error.message;
  }
  return fallback;
}
