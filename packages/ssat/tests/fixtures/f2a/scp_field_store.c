#include <stddef.h>
#define MSG_SET_PROFILE 41

typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;

static Reg g_table[8];
static int on_scp(void *payload) { return payload == NULL; }

/* separate field-store statements to one slot (no aggregate initializer) */
static void init(void) {
    g_table[0].action = MSG_SET_PROFILE;
    g_table[0].fn = on_scp;
}
