package br.com.ibero.nr17;

import android.graphics.Bitmap;
import android.graphics.PointF;

import com.google.android.gms.tasks.OnCompleteListener;
import com.google.android.gms.tasks.OnFailureListener;
import com.google.android.gms.tasks.OnSuccessListener;
import com.google.android.gms.tasks.Task;

import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.pose.Pose;
import com.google.mlkit.vision.pose.PoseDetection;
import com.google.mlkit.vision.pose.PoseDetector;
import com.google.mlkit.vision.pose.PoseLandmark;
import com.google.mlkit.vision.pose.defaults.PoseDetectorOptions;

import org.json.JSONObject;

import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Ponte Android nativa para o Python/Kivy.
 *
 * Recebe um frame RGBA reduzido, executa ML Kit Pose em STREAM_MODE
 * e expõe o resultado mais recente como JSON. Somente um frame é
 * processado por vez, evitando backlog e travamento.
 */
public class PoseAnalyzer {
    private final PoseDetector detector;
    private final AtomicBoolean busy = new AtomicBoolean(false);
    private final AtomicLong sequence = new AtomicLong(0);
    private volatile String latestJson = "";

    public PoseAnalyzer() {
        PoseDetectorOptions options =
            new PoseDetectorOptions.Builder()
                .setDetectorMode(PoseDetectorOptions.STREAM_MODE)
                .build();

        detector = PoseDetection.getClient(options);
    }

    public boolean isBusy() {
        return busy.get();
    }

    public String getLatestJson() {
        return latestJson == null ? "" : latestJson;
    }

    public boolean analyze(byte[] rgba, int width, int height, int rotationDegrees) {
        if (rgba == null || width <= 1 || height <= 1) {
            return false;
        }
        if (rgba.length < width * height * 4) {
            return false;
        }
        if (!busy.compareAndSet(false, true)) {
            return false;
        }

        final long started = System.currentTimeMillis();
        final Bitmap bitmap;

        try {
            int pixelCount = width * height;
            int[] colors = new int[pixelCount];

            int src = 0;
            for (int i = 0; i < pixelCount; i++) {
                int r = rgba[src] & 0xFF;
                int g = rgba[src + 1] & 0xFF;
                int b = rgba[src + 2] & 0xFF;
                int a = rgba[src + 3] & 0xFF;
                if (a == 0) a = 255;
                colors[i] = (a << 24) | (r << 16) | (g << 8) | b;
                src += 4;
            }

            bitmap = Bitmap.createBitmap(colors, width, height, Bitmap.Config.ARGB_8888);
        } catch (Exception exc) {
            busy.set(false);
            latestJson = errorJson(exc, started);
            return false;
        }

        final int rotation = normalizeRotation(rotationDegrees);
        final int outputWidth = (rotation == 90 || rotation == 270) ? height : width;
        final int outputHeight = (rotation == 90 || rotation == 270) ? width : height;

        InputImage image = InputImage.fromBitmap(bitmap, rotation);

        detector.process(image)
            .addOnSuccessListener(new OnSuccessListener<Pose>() {
                @Override
                public void onSuccess(Pose pose) {
                    latestJson = buildPoseJson(
                        pose,
                        width,
                        height,
                        outputWidth,
                        outputHeight,
                        rotation,
                        started
                    );
                }
            })
            .addOnFailureListener(new OnFailureListener() {
                @Override
                public void onFailure(Exception e) {
                    latestJson = errorJson(e, started);
                }
            })
            .addOnCompleteListener(new OnCompleteListener<Pose>() {
                @Override
                public void onComplete(Task<Pose> task) {
                    try {
                        bitmap.recycle();
                    } catch (Exception ignored) {}
                    busy.set(false);
                }
            });

        return true;
    }

    private static int normalizeRotation(int degrees) {
        int d = ((degrees % 360) + 360) % 360;
        if (d < 45) return 0;
        if (d < 135) return 90;
        if (d < 225) return 180;
        if (d < 315) return 270;
        return 0;
    }

    private String errorJson(Exception exc, long started) {
        try {
            JSONObject root = new JSONObject();
            root.put("seq", sequence.incrementAndGet());
            root.put("detected", false);
            root.put("inferenceMs", Math.max(0, System.currentTimeMillis() - started));
            root.put("error", exc == null ? "erro desconhecido" : String.valueOf(exc.getMessage()));
            return root.toString();
        } catch (Exception ignored) {
            return "{\"detected\":false}";
        }
    }

    private String buildPoseJson(
        Pose pose,
        int sourceWidth,
        int sourceHeight,
        int outputWidth,
        int outputHeight,
        int rotation,
        long started
    ) {
        try {
            JSONObject root = new JSONObject();
            root.put("seq", sequence.incrementAndGet());
            root.put("sourceWidth", sourceWidth);
            root.put("sourceHeight", sourceHeight);
            root.put("outputWidth", outputWidth);
            root.put("outputHeight", outputHeight);
            root.put("rotation", rotation);
            root.put("inferenceMs", Math.max(0, System.currentTimeMillis() - started));

            boolean detected = pose != null && !pose.getAllPoseLandmarks().isEmpty();
            root.put("detected", detected);

            JSONObject points = new JSONObject();

            if (detected) {
                add(points, "nose", pose, PoseLandmark.NOSE, outputWidth, outputHeight);

                add(points, "left_ear", pose, PoseLandmark.LEFT_EAR, outputWidth, outputHeight);
                add(points, "right_ear", pose, PoseLandmark.RIGHT_EAR, outputWidth, outputHeight);

                add(points, "left_shoulder", pose, PoseLandmark.LEFT_SHOULDER, outputWidth, outputHeight);
                add(points, "right_shoulder", pose, PoseLandmark.RIGHT_SHOULDER, outputWidth, outputHeight);
                add(points, "left_elbow", pose, PoseLandmark.LEFT_ELBOW, outputWidth, outputHeight);
                add(points, "right_elbow", pose, PoseLandmark.RIGHT_ELBOW, outputWidth, outputHeight);
                add(points, "left_wrist", pose, PoseLandmark.LEFT_WRIST, outputWidth, outputHeight);
                add(points, "right_wrist", pose, PoseLandmark.RIGHT_WRIST, outputWidth, outputHeight);

                add(points, "left_pinky", pose, PoseLandmark.LEFT_PINKY, outputWidth, outputHeight);
                add(points, "right_pinky", pose, PoseLandmark.RIGHT_PINKY, outputWidth, outputHeight);
                add(points, "left_index", pose, PoseLandmark.LEFT_INDEX, outputWidth, outputHeight);
                add(points, "right_index", pose, PoseLandmark.RIGHT_INDEX, outputWidth, outputHeight);
                add(points, "left_thumb", pose, PoseLandmark.LEFT_THUMB, outputWidth, outputHeight);
                add(points, "right_thumb", pose, PoseLandmark.RIGHT_THUMB, outputWidth, outputHeight);

                add(points, "left_hip", pose, PoseLandmark.LEFT_HIP, outputWidth, outputHeight);
                add(points, "right_hip", pose, PoseLandmark.RIGHT_HIP, outputWidth, outputHeight);
                add(points, "left_knee", pose, PoseLandmark.LEFT_KNEE, outputWidth, outputHeight);
                add(points, "right_knee", pose, PoseLandmark.RIGHT_KNEE, outputWidth, outputHeight);
                add(points, "left_ankle", pose, PoseLandmark.LEFT_ANKLE, outputWidth, outputHeight);
                add(points, "right_ankle", pose, PoseLandmark.RIGHT_ANKLE, outputWidth, outputHeight);
            }

            root.put("landmarks", points);
            return root.toString();
        } catch (Exception exc) {
            return errorJson(exc, started);
        }
    }

    private void add(
        JSONObject points,
        String name,
        Pose pose,
        int landmarkType,
        int outputWidth,
        int outputHeight
    ) {
        try {
            PoseLandmark lm = pose.getPoseLandmark(landmarkType);
            if (lm == null) return;

            PointF p = lm.getPosition();

            // O ML Kit entrega as posições no espaço da imagem já orientada.
            // Além das coordenadas brutas, devolvemos coordenadas normalizadas
            // para o overlay do Kivy não depender da resolução do frame.
            float xn = outputWidth > 0 ? p.x / (float) outputWidth : 0f;
            float yn = outputHeight > 0 ? p.y / (float) outputHeight : 0f;

            JSONObject obj = new JSONObject();
            obj.put("x", clamp01(xn));
            obj.put("y", clamp01(yn));
            obj.put("rawX", p.x);
            obj.put("rawY", p.y);
            obj.put("z", lm.getPosition3D().getZ());
            obj.put("c", lm.getInFrameLikelihood());
            points.put(name, obj);
        } catch (Exception ignored) {}
    }

    private static float clamp01(float v) {
        return Math.max(0f, Math.min(1f, v));
    }

    public void close() {
        try {
            detector.close();
        } catch (Exception ignored) {}
        busy.set(false);
    }
}
