/* TC3: designated-initializer registration (the canonical case).
 * Equivalent to the positional `{ ACTION_REMOTE_START, remote_handler }` form,
 * which already resolves — this exercises the designated syntax. */
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;
typedef enum { ACTION_REMOTE_START = 3 } OcppAction;
static int remote_handler(void *payload) { return payload == NULL; }
static Reg handlers[] = {
    { .action = ACTION_REMOTE_START, .fn = remote_handler }
};
