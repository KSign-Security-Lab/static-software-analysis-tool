#include <stddef.h>
#define MSG_SET_PROFILE 41
typedef int (*HandlerFn)(void *);
static int g_count = 0;
static int on_scp(void *payload) { return payload == NULL; }
/* receives (id, fn) but never stores fn into a table -> store not reached */
static void register_handler(int action, HandlerFn fn) { g_count += action; (void)fn; }
static void init(void) { register_handler(MSG_SET_PROFILE, on_scp); }
