package org.agal.research

import android.app.Activity
import android.content.ClipData
import android.content.Intent
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.UUID

class MainActivity : FlutterActivity() {
    private var pending: MethodChannel.Result? = null
    private var source: File? = null
    private var operation = ""

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "org.agal.research/documents")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "saveDocument" -> {
                            check(pending == null) { "A document operation is already open" }
                            source = privateFile(call.argument<String>("path")!!)
                            pending = result; operation = "save"
                            val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                                addCategory(Intent.CATEGORY_OPENABLE)
                                type = call.argument<String>("mime") ?: "text/csv"
                                putExtra(Intent.EXTRA_TITLE, call.argument<String>("name") ?: "survey-responses.csv")
                            }
                            startActivityForResult(intent, 701)
                        }
                        "pickMedia", "pickBackup" -> {
                            check(pending == null) { "A document operation is already open" }
                            pending = result; operation = "pick"
                            val intent = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                                addCategory(Intent.CATEGORY_OPENABLE)
                                type = "*/*"
                                putExtra(Intent.EXTRA_MIME_TYPES, if (call.method == "pickBackup") arrayOf("application/json", "application/octet-stream") else arrayOf("image/jpeg", "image/png", "audio/mp4", "audio/mpeg", "audio/wav", "application/pdf"))
                            }
                            startActivityForResult(intent, 701)
                        }
                        "shareFile" -> {
                            val file = privateFile(call.argument<String>("path")!!)
                            val directory = File(cacheDir, "exports").apply { mkdirs() }
                            val name = File(call.argument<String>("name") ?: "survey-responses.csv").name
                            val copy = File(directory, "${UUID.randomUUID()}-$name")
                            file.copyTo(copy, overwrite = false)
                            val uri = FileProvider.getUriForFile(this, "$packageName.exports", copy)
                            val intent = Intent(Intent.ACTION_SEND).apply {
                                type = call.argument<String>("mime") ?: "text/csv"
                                putExtra(Intent.EXTRA_STREAM, uri)
                                clipData = ClipData.newRawUri("Survey export", uri)
                                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            }
                            startActivity(Intent.createChooser(intent, "Share survey export"))
                            result.success(true)
                        }
                        else -> result.notImplemented()
                    }
                } catch (e: Exception) {
                    pending = null; source = null
                    result.error("document_error", e.message, null)
                }
            }
    }

    private fun privateFile(path: String): File {
        val file = File(path).canonicalFile
        val allowed = File(applicationInfo.dataDir).canonicalPath + File.separator
        require(file.path.startsWith(allowed) && file.isFile) { "Expected an app-private file" }
        return file
    }

    @Deprecated("Android activity result callback required by FlutterActivity")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != 701) return
        val result = pending ?: return
        pending = null
        try {
            val uri = data?.data
            if (resultCode != Activity.RESULT_OK || uri == null) {
                result.success(if (operation == "save") false else null)
                return
            }
            if (operation == "save") {
                val file = source ?: error("Export source unavailable after activity restart; retry save")
                val output = contentResolver.openOutputStream(uri, "wt") ?: error("Document provider is not writable")
                output.use { destination -> file.inputStream().use { it.copyTo(destination) } }
                result.success(true)
            } else {
                var name = "attachment"
                contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use {
                    if (it.moveToFirst()) name = it.getString(0)
                }
                val file = File(cacheDir, "picked-${UUID.randomUUID()}")
                val input = contentResolver.openInputStream(uri) ?: error("Document provider is not readable")
                // Bounded copy protects app storage from unexpectedly large provider content.
                input.use { src -> file.outputStream().use { dst ->
                    val buffer = ByteArray(8192); var total = 0L
                    while (true) {
                        val read = src.read(buffer)
                        if (read < 0) break
                        total += read
                        require(total <= 100L * 1024L * 1024L) { "Document exceeds 100 MiB" }
                        dst.write(buffer, 0, read)
                    }
                } }
                result.success(mapOf("path" to file.path, "name" to name, "mime" to (contentResolver.getType(uri) ?: "application/octet-stream")))
            }
        } catch (e: Exception) {
            result.error("document_error", e.message, null)
        } finally { source = null }
    }
}
