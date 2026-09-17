/*
 * Four units with the same defect and four different answers about whether it
 * runs. Separate from `fixtures/sample/`, which is the scored eval set for
 * *exploitability*: its file and chunk counts are asserted and quoted in the
 * README, and reachability is a different property that should not perturb it.
 *
 * Ground truth (agent.index.reach):
 *   handle_request           live          called from main
 *   store_payload_dead       unreachable   static, and nothing names it at all
 *   store_payload_via_table  unknown       static, but its address is taken
 *   store_payload_exported   unreferenced  nothing here calls it; something
 *                                          outside this tree still might
 *
 * Every one of them holds the same unbounded memcpy. That is the point: reach
 * is orthogonal to the defect, so none of these may ever be *suppressed* --
 * only labelled.
 */
#include <string.h>
#include <stddef.h>

#define SLOT 64

typedef struct {
    const char *body;
    size_t body_len;
} Request;

typedef void (*handler_fn)(const Request *);

static char g_slot[SLOT];

/* static, never called, and its name appears nowhere else in the tree. */
static void store_payload_dead(const Request *req)
{
    memcpy(g_slot, req->body, req->body_len);
}

/*
 * static and never called *directly* -- but registered below. The trap: an
 * index that reads "no callers" as "dead" hides this one, and it is as live as
 * anything reached through the table.
 */
static void store_payload_via_table(const Request *req)
{
    memcpy(g_slot, req->body, req->body_len);
}

static handler_fn g_handlers[] = {
    store_payload_via_table,
};

/* Not static: nothing in this tree calls it, but a caller outside could. */
void store_payload_exported(const Request *req)
{
    memcpy(g_slot, req->body, req->body_len);
}

void handle_request(const Request *req)
{
    g_handlers[0](req);
}

int main(void)
{
    Request req = {0};
    handle_request(&req);
    return 0;
}
