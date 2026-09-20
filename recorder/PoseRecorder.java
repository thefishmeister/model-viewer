package @PACKAGE@;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.model.HumanoidModel;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.renderer.entity.state.HumanoidRenderState;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.HumanoidArm;
import net.minecraft.world.item.ItemStack;
import org.joml.Matrix4f;

/**
 * Model viewer pose recorder. While a held item is drawn in game (third person, or another player or mob holding it) this
 * records how the game actually poses the body and where it puts the item, both standing still and through each attack
 * swing, and writes a pose profile the model viewer plays back:
 * {@code <game dir>/model-viewer/poses/<item>.pose.json}. It records only in a development environment, or with
 * {@code -Dmodelviewer.record=true}, and never changes what is drawn. Installed by the model-viewer plugin; safe to delete.
 * The profile format is described in the plugin's POSES.md.
 */
public final class PoseRecorder {
    private static final int BINS = 40;
    private static final boolean ON = FabricLoader.getInstance().isDevelopmentEnvironment() || Boolean.getBoolean("modelviewer.record");
    private static final String[] AXES = {"x", "y", "z", "px", "py", "pz"};
    private static final String[] PARTS = {"head", "body", "rightArm", "leftArm", "rightLeg", "leftLeg"};
    private static final int[] MIRROR = {0, 1, 3, 2, 5, 4};
    private static final Map<String, Rec> RECS = new HashMap<>();
    private static final ThreadLocal<Matrix4f> ENTRY = new ThreadLocal<>();
    private static long lastWrite;

    static {
        if (ON) Runtime.getRuntime().addShutdownHook(new Thread(PoseRecorder::writeAll, "model-viewer-pose-writer"));
    }

    private static final class Rec {
        float[][] carry;
        float[] carryMatrix;
        final float[][][] swing = new float[BINS][][];
        final float[][] swingMatrix = new float[BINS][];
        float ticks, startAge, lastAge, lastAttack;
        boolean dirty;
    }

    private PoseRecorder() {}

    private static Rec rec(ItemStack stack) {
        return RECS.computeIfAbsent(BuiltInRegistries.ITEM.getKey(stack.getItem()).toString(), k -> new Rec());
    }

    private static boolean still(HumanoidRenderState state) {
        return state.walkAnimationSpeed < 0.02F && !state.isCrouching && !state.isVisuallySwimming && !state.isFallFlying;
    }

    /** After the game has finished posing the model: samples every part. */
    public static void sampleParts(HumanoidModel<?> model, HumanoidRenderState state) {
        if (!ON) return;
        boolean right = state.mainArm == HumanoidArm.RIGHT;
        ItemStack held = right ? state.rightHandItemStack : state.leftHandItemStack;
        if (held == null || held.isEmpty()) return;
        Rec r = rec(held);
        ModelPart[] parts = {model.head, model.body, model.rightArm, model.leftArm, model.rightLeg, model.leftLeg};
        float[][] s = new float[6][];
        for (int i = 0; i < 6; i++) {
            ModelPart p = parts[right ? i : MIRROR[i]];      // a left-handed wielder is recorded mirrored, as a right-handed one
            s[i] = right ? new float[]{p.xRot, p.yRot, p.zRot, p.x, p.y, p.z} : new float[]{p.xRot, -p.yRot, -p.zRot, -p.x, p.y, p.z};
        }
        float attack = state.attackTime;
        if (attack > 0) {
            if (r.lastAttack <= 0) r.startAge = state.ageInTicks;
            r.lastAge = state.ageInTicks;
            r.lastAttack = attack;
            r.swing[Math.min(BINS - 1, (int) (attack * BINS))] = s;
            r.dirty = true;
        } else {
            if (r.lastAttack > 0.3F) r.ticks = Math.max(1, (r.lastAge - r.startAge) / r.lastAttack);
            r.lastAttack = 0;
            if (still(state)) { r.carry = s; r.dirty = true; }
        }
        maybeWrite();
    }

    /** At the top of the hand-item layer: the model-to-world matrix before the hand's own transforms. */
    public static void enterItemLayer(com.mojang.blaze3d.vertex.PoseStack pose) {
        if (ON) ENTRY.set(new Matrix4f(pose.last().pose()));
    }

    /** Just before the item is drawn: where the game put it, in the character's model space. */
    public static void sampleItem(HumanoidRenderState state, HumanoidArm arm, ItemStack stack, com.mojang.blaze3d.vertex.PoseStack pose) {
        Matrix4f entry = ENTRY.get();
        if (!ON || entry == null || stack.isEmpty() || arm != state.mainArm) return;
        Matrix4f m = new Matrix4f(entry).invert().mul(pose.last().pose());
        if (arm == HumanoidArm.LEFT) {
            Matrix4f flip = new Matrix4f().scaling(-1, 1, 1);
            m = new Matrix4f(flip).mul(m).mul(flip);
        }
        float[] out = new float[16];
        m.get(out);
        Rec r = rec(stack);
        if (state.attackTime > 0) r.swingMatrix[Math.min(BINS - 1, (int) (state.attackTime * BINS))] = out;
        else if (still(state)) r.carryMatrix = out;
        r.dirty = true;
    }

    private static void maybeWrite() {
        long now = System.currentTimeMillis();
        if (now - lastWrite > 2000) { lastWrite = now; writeAll(); }
    }

    private static synchronized void writeAll() {
        for (var entry : RECS.entrySet()) {
            Rec r = entry.getValue();
            if (!r.dirty) continue;
            r.dirty = false;
            try {
                Path file = FabricLoader.getInstance().getGameDir().resolve("model-viewer/poses")
                        .resolve(entry.getKey().substring(entry.getKey().indexOf(':') + 1).replace('/', '_') + ".pose.json");
                Files.createDirectories(file.getParent());
                Files.writeString(file, new GsonBuilder().setPrettyPrinting().create().toJson(profile(entry.getKey(), r)));
            } catch (IOException | RuntimeException e) {
                System.err.println("[model-viewer] could not write the pose for " + entry.getKey() + ": " + e);
            }
        }
    }

    private static float round(float v) { return Math.round(v * 100000F) / 100000F; }

    private static JsonArray matrix(float[] m) {
        JsonArray a = new JsonArray();
        for (float v : m) a.add(round(v));
        return a;
    }

    private static JsonObject profile(String id, Rec r) {
        float[][] carry = r.carry;
        if (carry == null) for (float[][] s : r.swing) if (s != null) { carry = s; break; }
        JsonObject root = new JsonObject();
        root.addProperty("item", id);
        root.addProperty("source", "Recorded in game by PoseRecorder.");
        root.addProperty("recorded", true);
        JsonObject carryJson = new JsonObject();
        if (carry != null) {
            for (int i = 0; i < 6; i++) {
                JsonObject part = new JsonObject();
                for (int a = 0; a < 6; a++) part.addProperty(AXES[a], round(carry[i][a]));
                carryJson.add(PARTS[i], part);
            }
        }
        float[] carryMatrix = r.carryMatrix;
        if (carryMatrix == null) for (float[] m : r.swingMatrix) if (m != null) { carryMatrix = m; break; }
        if (carryMatrix != null) carryJson.add("itemMatrix", matrix(carryMatrix));
        root.add("carry", carryJson);

        JsonObject tracks = new JsonObject();
        for (int i = 0; i < 6 && carry != null; i++) {
            for (int a = 0; a < 6; a++) {
                JsonArray keys = new JsonArray();
                boolean moves = false;
                for (int b = 0; b < BINS; b++) {
                    if (r.swing[b] == null) continue;
                    if (Math.abs(r.swing[b][i][a] - carry[i][a]) > 1.0E-3F) moves = true;
                    JsonArray key = new JsonArray();
                    key.add(round((b + 0.5F) / BINS));
                    key.add(round(r.swing[b][i][a]));
                    keys.add(key);
                }
                if (moves) tracks.add(PARTS[i] + "." + AXES[a], keys);
            }
        }
        JsonArray matrices = new JsonArray();
        for (int b = 0; b < BINS; b++) {
            if (r.swingMatrix[b] == null) continue;
            JsonArray key = new JsonArray();
            key.add(round((b + 0.5F) / BINS));
            key.add(matrix(r.swingMatrix[b]));
            matrices.add(key);
        }
        if (tracks.size() > 0 || matrices.size() > 0) {
            JsonObject swing = new JsonObject();
            swing.addProperty("ticks", Math.round(r.ticks > 0 ? r.ticks : 12));
            swing.addProperty("gap", 10);
            swing.add("tracks", tracks);
            if (matrices.size() > 0) swing.add("itemMatrix", matrices);
            JsonObject animations = new JsonObject();
            animations.add("swing", swing);
            root.add("animations", animations);
        }
        return root;
    }
}
