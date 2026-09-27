export class ExecutorError extends Error {
  constructor(code, message, { retryable = false, status = 400, details = {} } = {}) {
    super(message);
    this.name = "ExecutorError";
    this.code = code;
    this.retryable = retryable;
    this.status = status;
    this.details = details;
  }
}

export function publicError(error) {
  if (error instanceof ExecutorError) {
    return {
      code: error.code,
      message: error.message,
      retryable: error.retryable,
      details: error.details,
    };
  }
  return {
    code: error?.code === "COMMAND_OUTPUT_LIMIT" ? "COMMAND_OUTPUT_LIMIT" : "EXECUTOR_INTERNAL_ERROR",
    message: error?.code === "COMMAND_OUTPUT_LIMIT" ? error.message : "The SSH executor could not complete the request",
    retryable: true,
    details: {},
  };
}
