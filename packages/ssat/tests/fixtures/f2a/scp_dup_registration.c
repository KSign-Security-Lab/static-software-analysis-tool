#include <stddef.h>
#define MSG_SET_PROFILE 41

typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;

static int on_scp(void *payload) { return payload == NULL; }

/* two registrations for the SAME action -> SAME callback */
static Reg g_table[] = {
    { MSG_SET_PROFILE, on_scp },
    { 41, on_scp }
};
