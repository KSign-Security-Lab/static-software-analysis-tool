#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define MSG_SET_PROFILE 41
#define PROFILE_BUFFER_SIZE 64

typedef struct { const char *schedule; size_t schedule_length; } ChargingSchedule;
typedef struct { int stack_level; ChargingSchedule charging_schedule; } ChargingProfile;
typedef struct { int connector_id; ChargingProfile *profile; } SetProfileRequest;
typedef struct { uint16_t message_type; void *payload; } OcppFrame;
typedef int (*MessageHandler)(void *payload);
typedef struct { uint16_t message_type; MessageHandler callback; } HandlerEntry;

static char g_profile_buffer[PROFILE_BUFFER_SIZE];

static int copy_profile_bytes(char *destination, const char *source, size_t length) {
    memcpy(destination, source, length);
    return 0;
}
static size_t calculate_copy_length(const ChargingProfile *profile) {
    if (profile == NULL) return 0;
    return profile->charging_schedule.schedule_length;
}
static const char *resolve_schedule(const SetProfileRequest *request) {
    if (request == NULL || request->profile == NULL) return NULL;
    return request->profile->charging_schedule.schedule;
}
static int process_configuration(void *payload) {
    SetProfileRequest *request = (SetProfileRequest *)payload;
    const char *schedule;
    size_t copy_length;
    if (request == NULL || request->profile == NULL) return -1;
    schedule = resolve_schedule(request);
    copy_length = calculate_copy_length(request->profile);
    if (schedule == NULL) return -1;
    if (request->connector_id == 0) {
        if (copy_length >= PROFILE_BUFFER_SIZE) return -1;
    }
    return copy_profile_bytes(g_profile_buffer, schedule, copy_length);
}
static HandlerEntry g_handler_table[] = {
    { 1, NULL },
    { MSG_SET_PROFILE, process_configuration },
    { 77, NULL }
};
static int route_frame(const OcppFrame *frame) {
    size_t handler_count = sizeof(g_handler_table) / sizeof(g_handler_table[0]);
    if (frame == NULL) return -1;
    for (size_t index = 0; index < handler_count; index++) {
        HandlerEntry *entry = &g_handler_table[index];
        if (entry->message_type != frame->message_type) continue;
        if (entry->callback == NULL) return -1;
        return entry->callback(frame->payload);
    }
    return -1;
}
