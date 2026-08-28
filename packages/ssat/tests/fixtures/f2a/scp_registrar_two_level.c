#include <stddef.h>
#define MSG_SET_PROFILE 41
typedef int (*HandlerFn)(void *);
typedef struct { int action; HandlerFn fn; } Reg;
static Reg g_table[8];
static int g_n = 0;
static int on_scp(void *payload) { return payload == NULL; }
static void store(int slot, int action, HandlerFn fn) {
    g_table[slot].action = action;
    g_table[slot].fn = fn;
}
/* registrar delegates to store (depth 2) */
static void register_handler(int action, HandlerFn fn) { store(g_n++, action, fn); }
static void init(void) { register_handler(MSG_SET_PROFILE, on_scp); }
