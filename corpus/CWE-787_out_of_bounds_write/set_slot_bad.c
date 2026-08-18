#include <stddef.h>

void set_slot_bad(int *slots, int index, int value) {
    /* index arrives from the request and is written straight through */
    slots[index] = value;
}
