import { admin } from "./firebase";

export async function cleanupPathByTimestamp(
  homeId: string,
  historyPath: string,
  cutoffMs: number,
  updates: Record<string, null>
): Promise<number> {
  const pathRef = admin.database().ref(`/homes/${homeId}/history/${historyPath}`);
  const oldLogsSnap = await pathRef
    .orderByChild("timestamp_ms")
    .endAt(cutoffMs)
    .get();

  if (!oldLogsSnap.exists()) {
    return 0;
  }

  let deletedCount = 0;

  oldLogsSnap.forEach((child) => {
    if (!child.key) {
      return false;
    }

    updates[`/homes/${homeId}/history/${historyPath}/${child.key}`] = null;
    deletedCount++;
    return false;
  });

  return deletedCount;
}
