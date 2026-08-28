#include <stddef.h>

void set_slot_fixed(int *slots, size_t count, int index, int value) {
    /* both ends checked, and index is compared as an unsigned quantity */
    if (index < 0 || (size_t)index >= count) return;
    slots[index] = value;
}
