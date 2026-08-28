#include <stddef.h>
#define MSG_SET_PROFILE 41

typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;

static int handler_a(void *payload) { return payload == NULL; }
static int handler_b(void *payload) { return payload == NULL; }

/* two rows for the SAME action id (41) -> DIFFERENT callbacks: a conflicting table */
static Reg g_table[] = {
    { 41, handler_a },
    { MSG_SET_PROFILE, handler_b }
};
