#include <stdlib.h>

void fill_table_fixed(int n) {
    /* the last index written is n - 1 */
    int *table = malloc((size_t)n * sizeof(int));
    if (table == NULL) return;
    for (int i = 0; i < n; i++) table[i] = i;
    publish(table, n);
}
